"""ShotSpec -> CompiledShot: the deterministic scene compiler for the current engine (blender_showcase_v1).

Resolves semantic assets, actions, camera, look, events and protection rules into everything the existing proven
stages consume: the ActionTimeline, the camera move (and its samples), the Blender builder's scene_build config, the
CompositeManifest, the LTX job (workflow + overrides + composed prompt), the grade, the semantic-object / mask /
policy map, the QC contract and the pipeline stage list. Same spec + same registry -> identical CompiledShot.
"""

from __future__ import annotations

import json
from fractions import Fraction

from onecreations.blender_bridge import REPO_ROOT
from onecreations.contracts.composite import CompositeManifest
from onecreations.contracts.director import (CompiledShot, GenerationJob, Placement, ResolvedEvent, SemanticObject,
                                             ShotSpec, Stage)
from onecreations.director import actions as act
from onecreations.director import camera as cam
from onecreations.director import policies as pol
from onecreations.director import qc
from onecreations.director.prompt import compose_prompt
from onecreations.director.registry import Registry
from onecreations.director.validate import validate_spec
from onecreations.hashing import content_hash, file_sha256
from onecreations.shotpkg.issues import Issue, has_errors
from onecreations.timebase import format_time

COMPILER = "onecreations.director.compiler/1"
ENGINE_PREFIX = {"blender_showcase_v1": "sc_"}
# compositing profile protected_layers_v1: how effect components are grouped into rendered layers (technical, D)
EFFECT_LAYERS = {
    "impact_fx": {"collections": ["fx_impact"], "order": 1, "components": ["dust", "debris", "sparks", "cracks"],
                  "render": {"holdout_others": True, "motion_blur_shutter": 0.5, "samples": 128}, "blend": "over"},
    "impact_flash": {"collections": ["fx_flash"], "order": 2, "components": ["flash"],
                     "render": {"holdout_others": False, "motion_blur_shutter": None, "samples": 96,
                                "light_only": ["fx_flash_light"]}, "blend": "add"},
}
FX_DEFAULTS = {"seed": 23, "dust_density": 1.6, "dust_decay_s": 0.6}


class CompileError(ValueError):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("; ".join(f"{i.code}: {i.message}" for i in issues if i.severity == "error"))


def spec_hash(spec: ShotSpec) -> str:
    return content_hash(spec.model_dump(mode="json"))


def _placement(c, reg) -> Placement:
    return c.placement or Placement(**reg.get(c.asset).data["default_placement"])


def compile_shot(spec: ShotSpec, reg: Registry) -> CompiledShot:
    issues = validate_spec(spec, reg)
    if has_errors(issues):
        raise CompileError(issues)
    prefix = ENGINE_PREFIX[reg.engine]
    chars = {c.id: c for c in spec.characters}
    attacker = next(c for c in spec.characters if c.role == "attacker")
    defender = next(c for c in spec.characters if c.role == "defender")
    a_entry, d_entry = reg.get(attacker.asset), reg.get(defender.asset)
    role = {cid: cid.lower() for cid in chars}                       # timeline actor roles

    # actions -> events and timeline
    events: dict[str, int] = {}
    phases = []
    primary = next(a for a in spec.actions if a.preset == "mace_slam_v1")
    ordered = [primary] + [a for a in spec.actions if a is not primary]
    for a in ordered:
        entry = reg.get(a.preset)
        for name, frame in act.resolve_events(entry, a.params).items():
            events[f"{a.id}.{name}"] = frame
        phases += act.phases(entry, a.params, role[a.actor])
    p_entry = reg.get(primary.preset)
    timeline_id = prefix + primary.preset
    timeline = {"schema_version": 1, "id": timeline_id, "version": act.timeline_version(p_entry, primary.params),
                "duration": format_time(Fraction(spec.duration_frames, spec.fps)),
                "actors": {role[c.id]: reg.get(c.asset).data["oc_id"] for c in spec.characters},
                "phases": phases, "contacts": []}
    resolved = [ResolvedEvent(name=n, frame=f, time=Fraction(f, spec.fps)) for n, f in events.items()]

    # placements, camera
    a_pl, d_pl = _placement(attacker, reg), _placement(defender, reg)
    places = {attacker.id: a_pl, defender.id: d_pl}
    c_entry = reg.get(spec.camera.preset)
    anchor = places[spec.camera.target.anchor].position
    target = [anchor[i] + spec.camera.target.offset[i] for i in range(3)]
    move = cam.build_move(c_entry, spec.camera.variant, target, spec.camera.params)

    # effects -> components, layers (all keyed from semantic events)
    def frame_of(ref):
        return events[f"{ref.action}.{ref.event}"] + ref.offset_frames

    comps = {reg.get(ev.preset).data["component"]: ev for ev in spec.events}
    look = reg.get(spec.look.preset)
    fx = dict(FX_DEFAULTS, components=[c for c in ("dust", "debris", "sparks", "cracks") if c in comps],
              flash="flash" in comps,
              flash_energy_w=list(reg.get(comps["flash"].preset).data["energy_w"]) if "flash" in comps else [])
    layers = []
    policies = {}
    semantic = []
    for p in spec.props:
        w = reg.get(p.asset)
        rule_id, prov = pol.weapon_rule(spec, reg, p)
        oc_ids = [part["oc_id"] for part in w.data["parts"]] or [reg.get(chars[p.owner].asset).data["oc_id"]]
        passes = [part["pass_index"] for part in w.data["parts"]] or [reg.get(chars[p.owner].asset).data["pass_index"]]
        separable = bool(w.data["parts"])
        layer_id = None
        if rule_id:
            rs = reg.get(rule_id, "protection_rule").data["layer_settings"]
            layer_id = f"{p.id.lower()}_protect"
            moving = [reg.get(c.asset).data["oc_id"] for c in spec.characters if reg.get(c.asset).data["motion"] == "rigged"]
            layers.append({
                "id": layer_id, "kind": "protected_geometry", "objects": oc_ids, "render": dict(rs["render"]),
                "occlusion": "holdout", "order": 0, "grade": rs["grade"], "ghost_suppression": rs["ghost_suppression"],
                "ghost_mode": rs["ghost_mode"], "ghost_fill": rs["ghost_fill"], "ghost_band_px": rs["ghost_band_px"],
                "ghost_keep_objects": moving, "soften_px": rs["soften_px"],
                "protection": {"track_object": w.data["track_part"], "authored_speed_widths": rs["authored_speed_widths"],
                               "dilate_frames": rs["dilate_frames"], "raw_retention_below": None,
                               "include_frames": list(range(spec.duration_frames)) if rs["all_frames"] else []}})
        semantic.append(SemanticObject(id=p.id, kind="weapon", asset=p.asset, oc_ids=oc_ids, pass_indices=passes,
                                       mask_separable=separable, protected_layer=layer_id,
                                       policy=pol.policy_for("weapon", separable, rule_id, prov)))
        policies[p.id] = rule_id
    for lid, spec_l in EFFECT_LAYERS.items():
        used = [c for c in spec_l["components"] if c in comps]
        if not used:
            continue
        ref = comps[used[0]].trigger
        phase, edge = act.event_phase_edge(reg.get(next(a.preset for a in spec.actions if a.id == ref.action)),
                                           ref.event)
        start = frame_of(ref)
        dur = spec.duration_frames - start if reg.get(comps[used[0]].preset).data["duration"] == "to_end" else \
            int(reg.get(comps[used[0]].preset).data["duration"])
        layer = {"id": lid, "kind": "effect", "collections": spec_l["collections"], "render": dict(spec_l["render"]),
                 "occlusion": "holdout", "order": spec_l["order"],
                 "trigger": {"timeline": timeline_id, "phase": phase, "edge": edge}, "duration_frames": dur}
        if spec_l["blend"] != "over":
            layer["blend"] = spec_l["blend"]
        layers.append(layer)
        for c in used:
            ev = comps[c]
            semantic.append(SemanticObject(id=ev.id.upper(), kind="effect", asset=ev.preset, oc_ids=[],
                                           mask_source="effect_layer_alpha", mask_separable=len(used) == 1,
                                           depth="none", protected_layer=lid, policy=pol.policy_for("effect", False)))
    manifest = CompositeManifest.model_validate({"schema_version": 1, "id": f"{spec.id}_layers", "shot": spec.id,
                                                 "layers": layers})

    # characters and environment parts (masks + policies)
    for c in spec.characters:
        e = reg.get(c.asset)
        semantic.append(SemanticObject(id=c.id, kind="character", asset=c.asset, oc_ids=[e.data["oc_id"]],
                                       pass_indices=[e.data["pass_index"]], mask_separable=True,
                                       material_groups=e.data.get("material_groups", []),
                                       material_masks=e.data.get("material_masks", {}),
                                       policy=pol.policy_for("character", True)))
    env = reg.get(spec.environment.asset)
    for sid, part in env.data["semantic_objects"].items():
        semantic.append(SemanticObject(id=sid, kind="environment_part", asset=env.id, oc_ids=part["oc_ids"],
                                       pass_indices=part["pass_indices"], mask_separable=True,
                                       policy=pol.policy_for("environment_part", True)))

    # generation, grade
    gp = reg.get(spec.generation.profile)
    wf_path = REPO_ROOT / gp.data["workflow"]
    nodes = gp.data["nodes"]
    prompt = compose_prompt(spec, reg)
    overrides = {nodes["prompt"]: {"text": prompt}, nodes["seed"]: {"noise_seed": spec.generation.seed},
                 nodes["latent"]: {"width": spec.resolution[0], "height": spec.resolution[1],
                                   "length": spec.duration_frames}}
    job = GenerationJob(backend=gp.data["backend"], workflow=gp.data["workflow"], workflow_sha256=file_sha256(wf_path),
                        overrides=overrides, prompt=prompt, seed=spec.generation.seed, steps=int(gp.data["steps"]),
                        resolution=tuple(spec.resolution), frames=spec.duration_frames)
    grade = dict(reg.get(spec.grade.preset).data["finish"], **spec.grade.params)
    grade["shake"] = []
    if "jolt" in comps:
        start = frame_of(comps["jolt"].trigger)
        grade["shake"] = [[start + d, dx, dy] for d, dx, dy in reg.get(comps["jolt"].preset).data["offsets_px"]]

    scene_build = {
        "engine": reg.engine, "shot_id": spec.id, "timeline_id": timeline_id, "timeline_actors": timeline["actors"],
        "frames": spec.duration_frames, "fps": spec.fps, "resolution": list(spec.resolution),
        "root_at": list(a_pl.position), "asura_yaw_deg": a_pl.yaw_deg, "defender_at": list(d_pl.position),
        "defender_yaw_deg": d_pl.yaw_deg, "defender_scale": d_pl.scale, "camera_move": move,
        "sun": dict(look.data["sun"]), "look": dict(look.data["lighting"], **spec.look.params),
        "strike_frames": int(act.action_params(p_entry, primary.params)["strike_frames"]), "fx": fx,
        "layers": manifest.model_dump(mode="json", exclude_none=False),
        "attacker_asset": a_entry.data.get("builder_variant", a_entry.id),
        "material_index_pass": bool(a_entry.data.get("material_masks")),
    }
    ctx = {"required_events": ["CONTACT", "APEX"], "rig": a_entry.data["rig_oc_id"],
           "weapon_track": reg.get(next(p.asset for p in spec.props if p.asset == "heavy_mace_v1")).data["track_part"],
           "actors": [a_entry.data["oc_id"], d_entry.data["oc_id"]], "resolution": list(spec.resolution),
           "fps": spec.fps,
           "weapon_pass_indices": [pi for o in semantic if o.kind == "weapon" and o.mask_separable
                                   for pi in o.pass_indices]}
    stages = [
        Stage(id="parse", implemented=True, in_dry_run=True, notes="keyword_v1 interpreter (replaceable)"),
        Stage(id="plan", implemented=True, in_dry_run=True),
        Stage(id="validate", implemented=True, in_dry_run=True),
        Stage(id="compile", implemented=True, in_dry_run=True),
        Stage(id="build_scene", implemented=True, notes="Blender build_showcase_scene.py --config"),
        Stage(id="render_controls", implemented=True, notes="oc_export passes + make_controls depth"),
        Stage(id="first_frame", implemented=True, notes="Cycles still of frame 1 (render_stills.py)"),
        Stage(id="masks", implemented=True, notes="per-semantic-object masks from the object-index pass"),
        Stage(id="preflight_qc", implemented=True, notes="qc.evaluate_preflight"),
        Stage(id="generate", implemented=False, notes="proven stage exists (run_admission.ps1 + workflow); not "
                                                      "invoked by the D1 orchestrator"),
        Stage(id="post_qc", implemented=False, notes="contract only (post_generation checks)"),
        Stage(id="render_layers", implemented=False, notes="render_layers.py exists; not orchestrated in D1"),
        Stage(id="repair_composite", implemented=False, notes="hybrid_composite.py exists; not orchestrated in D1"),
        Stage(id="grade", implemented=False, notes="finish_grade.py exists; not orchestrated in D1"),
        Stage(id="deliver", implemented=False),
    ]
    notes = [f"{i.code}: {i.message}" for i in issues]
    return CompiledShot(shot_id=spec.id, compiler=COMPILER, spec_sha256=spec_hash(spec), registry_sha256=reg.sha256,
                        engine=reg.engine, frames=spec.duration_frames, fps=spec.fps, resolution=tuple(spec.resolution),
                        events=resolved, action_timeline=timeline, camera_move=move, scene_build=scene_build,
                        layers=manifest, generation=job, grade=grade, semantic_objects=semantic,
                        qc=qc.checks_for(spec.qc_profile, ctx), stages=stages, notes=notes)


def compiled_workflow(compiled: CompiledShot) -> dict:
    """The LTX API workflow the generation stage would submit: the profile's workflow with the overrides applied."""
    wf = json.loads((REPO_ROOT / compiled.generation.workflow).read_text(encoding="utf-8"))
    for node, inputs in compiled.generation.overrides.items():
        wf[node]["inputs"].update(inputs)
    return wf
