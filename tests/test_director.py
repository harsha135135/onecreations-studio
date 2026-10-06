"""D1 director foundation: registry, ShotSpec validation, events, camera, policies, compiler, Showcase v1
reproduction against the archived records, prompt interpreter, dry run (no processes)."""

import copy
import csv
import json
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from onecreations.contracts import ActionTimeline, CompositeManifest, ShotSpec
from onecreations.contracts.registry import AssetRegistry
from onecreations.director import actions as act
from onecreations.director import camera as cam
from onecreations.director import executor
from onecreations.director.compiler import CompileError, compile_shot, compiled_workflow
from onecreations.director.interpreter import interpret
from onecreations.director.planner import PlanError, plan_to_spec
from onecreations.director.registry import RegistryError, load_registry
from onecreations.director.validate import validate_spec
from tools.admission import hybrid_composite as hc

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE_SPEC = ROOT / "examples" / "director" / "showcase_v1.shotspec.json"
ARCHIVE = ROOT / "admission_records" / "showcase" / "2026-10-06_showcase-v1_"
PROMPT = ("Create a cinematic shot of a horned Asura attacking an ascetic defender with a mace in an ancient temple at "
          "dusk. Use a low orbit and push-in with dust and debris on impact.")


@pytest.fixture(scope="module")
def reg():
    return load_registry()


@pytest.fixture()
def spec_dict():
    return json.loads(SHOWCASE_SPEC.read_text(encoding="utf-8"))


def spec_of(d):
    return ShotSpec.model_validate(d)


def codes(issues):
    return {i.code for i in issues if i.severity == "error"}


# --- registry --------------------------------------------------------------------------------------------------

def test_registry_loads_only_real_entries(reg):
    kinds = {e.kind for e in reg.model.entries}
    assert kinds == {"character", "weapon", "environment", "action", "camera", "vfx", "look", "grade",
                     "generation_profile", "protection_rule"}
    assert reg.get("asura_showcase_v1", "character").data["oc_id"] == "sc_asura"
    assert reg.get("mace_slam_v1").data["events"]["CONTACT"] == {"frame": 23, "plus_param": "strike_frames"}
    with pytest.raises(RegistryError, match="no registry entry"):
        reg.get("dragon_v1")
    with pytest.raises(RegistryError, match="is a weapon"):
        reg.get("heavy_mace_v1", "character")
    assert (ROOT / reg.get("ltx25_union_768_v1").data["workflow"]).is_file()


def test_registry_rejects_missing_data_and_duplicates(reg):
    raw = reg.model.model_dump(mode="json")
    bad = copy.deepcopy(raw)
    del bad["entries"][0]["data"]["oc_id"]
    with pytest.raises(ValidationError, match="missing"):
        AssetRegistry.model_validate(bad)
    dup = copy.deepcopy(raw)
    dup["entries"].append(dup["entries"][0])
    with pytest.raises(ValidationError, match="duplicate registry ids"):
        AssetRegistry.model_validate(dup)


# --- validation --------------------------------------------------------------------------------------------------

def test_showcase_spec_is_valid(reg, spec_dict):
    assert codes(validate_spec(spec_of(spec_dict), reg)) == set()


def test_missing_asset_and_semantic_references_fail_clearly(reg, spec_dict):
    d = copy.deepcopy(spec_dict)
    d["props"][0]["asset"] = "great_sword_v1"
    assert "SPEC_UNKNOWN_ASSET" in codes(validate_spec(spec_of(d), reg))
    d = copy.deepcopy(spec_dict)
    d["props"][0]["asset"] = "asura_showcase_v1"
    assert "SPEC_WRONG_KIND" in codes(validate_spec(spec_of(d), reg))
    d = copy.deepcopy(spec_dict)
    d["actions"][0]["target"] = "RAVANA"
    assert "SPEC_TARGET_MISSING" in codes(validate_spec(spec_of(d), reg))
    d = copy.deepcopy(spec_dict)
    d["camera"]["target"]["anchor"] = "GHOST"
    assert "SPEC_CAMERA_TARGET" in codes(validate_spec(spec_of(d), reg))
    d = copy.deepcopy(spec_dict)
    d["props"] = d["props"][1:]                                   # no mace for the slam
    assert {"SPEC_WEAPON_MISSING", "ENGINE_PROPS"} <= codes(validate_spec(spec_of(d), reg))
    with pytest.raises(ValidationError, match="duplicate semantic"):
        spec_of(dict(spec_dict, props=spec_dict["props"] + [spec_dict["props"][0]]))


def test_rig_and_motion_compatibility(reg, spec_dict):
    d = copy.deepcopy(spec_dict)
    d["actions"][0]["actor"] = "DEFENDER"                         # the static ascetic cannot perform the rigged slam
    out = codes(validate_spec(spec_of(d), reg))
    assert "SPEC_ACTION_RIG_MISMATCH" in out
    d = copy.deepcopy(spec_dict)
    d["props"][0]["owner"] = "DEFENDER"                           # the mace needs the mace bone of the humanoid rig
    assert "SPEC_WEAPON_MOUNT" in codes(validate_spec(spec_of(d), reg))


def test_event_duration_resolution_camera_and_params(reg, spec_dict):
    d = copy.deepcopy(spec_dict)
    d["events"][0]["trigger"]["event"] = "IMPACT"
    with pytest.raises(ValidationError):                         # not an EventName
        spec_of(d)
    d = copy.deepcopy(spec_dict)
    d["events"][0]["trigger"]["action"] = "guard"                 # guard has no CONTACT
    assert "SPEC_EVENT_UNRESOLVABLE" in codes(validate_spec(spec_of(d), reg))
    d = copy.deepcopy(spec_dict)
    d["events"][0]["trigger"]["offset_frames"] = 3
    assert "ENGINE_EFFECT_TRIGGER" in codes(validate_spec(spec_of(d), reg))
    d = copy.deepcopy(spec_dict)
    d["duration_frames"] = 30
    assert "SPEC_DURATION" in codes(validate_spec(spec_of(d), reg))
    d = copy.deepcopy(spec_dict)
    d["resolution"] = [1280, 720]
    assert "SPEC_RESOLUTION_UNSUPPORTED" in codes(validate_spec(spec_of(d), reg))
    d = copy.deepcopy(spec_dict)
    d["camera"]["params"] = {"azimuth_deg": [-30.0, 30.0]}
    assert "SPEC_CAMERA_ENVELOPE" in codes(validate_spec(spec_of(d), reg))
    d = copy.deepcopy(spec_dict)
    d["actions"][0]["params"] = {"strike_frames": 12}
    assert "SPEC_PARAM" in codes(validate_spec(spec_of(d), reg))
    d = copy.deepcopy(spec_dict)
    d["characters"][1]["placement"]["position"] = [5.0, 9.0, 0.0]
    assert "SPEC_PLACEMENT_ZONE" in codes(validate_spec(spec_of(d), reg))
    with pytest.raises(CompileError, match="SPEC_PLACEMENT_ZONE"):
        compile_shot(spec_of(d), reg)


# --- events, camera, policies -------------------------------------------------------------------------------------

def test_action_events_and_contact_propagation(reg, spec_dict):
    slam = reg.get("mace_slam_v1")
    assert act.resolve_events(slam, {}) == {"START": 0, "GUARD_END": 7, "APEX": 23, "CONTACT": 29, "HOLD_END": 34,
                                            "RECOVERY_START": 34, "END": 48}
    assert act.resolve_events(slam, {"strike_frames": 9})["CONTACT"] == 32
    assert act.event_phase_edge(slam, "CONTACT") == ("impact", "start")
    d = copy.deepcopy(spec_dict)
    d["actions"][0]["params"] = {"strike_frames": 8}
    c = compile_shot(spec_of(d), reg)
    contact = next(e.frame for e in c.events if e.name == "strike.CONTACT")
    assert contact == 31
    fx = next(ly for ly in c.layers.layers if ly.id == "impact_fx")
    flash = next(ly for ly in c.layers.layers if ly.id == "impact_flash")
    for ly in (fx, flash):                                        # every dependent effect moved with the contact
        assert hc.trigger_frame(c.action_timeline.model_dump(mode="json"), ly.trigger.phase, ly.trigger.edge,
                                Fraction(24)) == contact
    assert fx.duration_frames == 49 - contact
    assert c.grade["shake"][0][0] == contact and c.scene_build["strike_frames"] == 8
    assert c.action_timeline.version == "1.0.0-strike8f"


def test_camera_preset_variants_and_envelope(reg):
    e = reg.get("orbit_push_v1")
    low = cam.build_move(e, "low", (-0.5, -3.9, 1.5), {})
    assert low["height_m"] == [2.25, 1.95] and low["lens_mm"] == 32.0 and cam.envelope_errors(e, low) == []
    high = cam.build_move(e, "high", (0, 0, 1.6), {})
    assert high["height_m"] == [3.6, 3.3] and high["lens_mm"] == 35.0 and cam.envelope_errors(e, high) == []
    bad = cam.build_move(e, "low", (0, 0, 1.5), {"radius_m": [9.0, 6.0], "lens_mm": 18.0})
    errs = cam.envelope_errors(e, bad)
    assert any("push-in" in m for m in errs) and any("lens" in m for m in errs)
    traj = cam.samples(low, 49, 24)
    assert len(traj.t) == 49 and traj.t[1] == pytest.approx(1 / 24)


def test_protection_policy_selection(reg, spec_dict):
    c = compile_shot(spec_of(spec_dict), reg)
    objs = {o.id: o for o in c.semantic_objects}
    assert objs["MACE"].policy.geometry == "protected" and objs["MACE"].policy.rule == "fast_weapon_v2"
    assert "P1" in objs["MACE"].policy.provenance and objs["MACE"].protected_layer == "mace_protect"
    assert objs["TRIDENT"].policy.geometry == "generative" and not objs["TRIDENT"].mask_separable
    assert objs["ASURA"].policy.appearance == "generative" and objs["ASURA"].policy.editable
    assert objs["IMPACT_DUST"].policy.appearance == "deterministic"
    assert objs["GROUND"].pass_indices == [7] and objs["RUBBLE"].pass_indices == [6, 16]
    d = copy.deepcopy(spec_dict)
    d["protection"] = [{"object": "MACE", "rule": "none"}]
    c2 = compile_shot(spec_of(d), reg)
    assert all(ly.kind != "protected_geometry" for ly in c2.layers.layers)


# --- compiler and Showcase v1 reproduction ---------------------------------------------------------------------------

def test_compilation_is_deterministic(reg, spec_dict):
    a = compile_shot(spec_of(spec_dict), reg).model_dump_json()
    b = compile_shot(spec_of(copy.deepcopy(spec_dict)), reg).model_dump_json()
    assert a == b


def test_showcase_v1_reproduction_against_archived_records(reg, spec_dict):
    c = compile_shot(spec_of(spec_dict), reg)
    arch = json.loads(Path(f"{ARCHIVE}shot_spec_final.json").read_text())
    sc, sb = arch["scene"], c.scene_build
    assert c.layers == CompositeManifest.model_validate(arch["layers"])
    assert c.action_timeline == ActionTimeline.model_validate(arch["choreography"]["action_timeline"])
    assert next(e.frame for e in c.events if e.name == "strike.CONTACT") == arch["choreography"]["impact_output_frame"]
    assert (sb["root_at"], sb["asura_yaw_deg"], sb["defender_at"], sb["defender_yaw_deg"]) == \
        (sc["root_at"], sc["asura_yaw_deg"], sc["defender_at"], sc["defender_yaw_deg"])
    assert sb["look"] == {k: list(v) if isinstance(v, (list, tuple)) else v for k, v in sc["look_params"].items()}
    assert sb["sun"] == sc["sun"] and list(c.resolution) == arch["resolution"]
    assert sb["camera_move"] == {k: v for k, v in arch["choreography"]["camera_move"].items() if k in sb["camera_move"]}
    rows = list(csv.DictReader(open(f"{ARCHIVE}camera_samples.csv")))
    traj = cam.samples(c.camera_move, c.frames, c.fps)
    assert np.abs(np.array([[float(r[k]) for k in "xyz"] for r in rows]) - traj.position).max() < 1e-9
    assert json.loads(Path(f"{ARCHIVE}finish.json").read_text())["params"] == c.grade
    wf = json.loads((ROOT / "workflows/ltx25/showcase_v1_api.json").read_text(encoding="utf-8"))
    assert compiled_workflow(c) == wf and c.generation.seed == 1000 and c.generation.steps == 8
    assert c.generation.prompt == wf["4"]["inputs"]["text"]
    assert {q.id for q in c.qc if q.stage == "preflight" and q.implemented} >= {"camera_contract", "depth_valid"}


# --- interpreter, planner, dry run -------------------------------------------------------------------------------

def test_prompt_interpreter_supported_example(reg):
    plan = interpret(PROMPT, reg)
    assert plan.supported and plan.unsupported == []
    assert plan.characters == {"attacker": "asura_v2", "defender": "ascetic_defender_v1"}
    assert plan.actions == {"attacker": "mace_slam_v1", "defender": "defender_guard_v1"}
    assert (plan.environment, plan.camera, plan.camera_variant, plan.look) == \
        ("temple_courtyard_v1", "orbit_push_v1", "low", "mythic_temple_dusk_v1")
    assert plan.vfx == ["impact_dust_v1", "debris_v1"] and plan.predicted_protection == {"MACE": "fast_weapon_v2"}
    spec = plan_to_spec(plan, reg, "d1_test")
    c = compile_shot(spec, reg)
    assert {e.name: e.frame for e in c.events}["strike.CONTACT"] == 29
    assert c.scene_build["fx"]["components"] == ["dust", "debris"] and not c.scene_build["fx"]["flash"]
    assert [ly.id for ly in c.layers.layers] == ["mace_protect", "impact_fx"]


def test_prompt_interpreter_names_slow_strike_and_block_warning(reg):
    plan = interpret("Lord Shiva stands inside an ancient ruined temple at dusk. A massive horned Asura slowly "
                     "attacks him with a mace. Shiva blocks using his trident. The impact throws dust and debris "
                     "into the air. Use a low cinematic orbit and push-in. Dark mythological fantasy film.", reg)
    assert plan.supported and plan.semantic_names == {"defender": "SHIVA", "attacker": "ASURA"}
    assert plan.action_params == {"attacker": {"strike_frames": 9}}
    assert any("block/parry" in w for w in plan.warnings)
    c = compile_shot(plan_to_spec(plan, reg), reg)
    assert c.action_timeline.actors == {"asura": "sc_asura", "shiva": "sc_defender"}
    assert next(e.frame for e in c.events if e.name == "strike.CONTACT") == 32


def test_prompt_interpreter_unsupported_example(reg):
    plan = interpret("A dragon flying over Tokyo at night, shot with an FPV drone", reg)
    assert not plan.supported
    assert {u.split(":")[0] for u in plan.unsupported} >= {"character", "environment", "action", "camera", "look"}
    with pytest.raises(PlanError, match="not supported"):
        plan_to_spec(plan, reg)
    assert not interpret("An asura attacks an ascetic with a sword in a temple", reg).supported


def test_dry_run_starts_no_process(reg, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a process was started during a dry run")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    out = executor.dry_run(request=PROMPT, reg=reg)
    assert out["status"] == "ok" and out["executed_processes"] == []
    stages = {s["id"]: s for s in out["compiled"]["stages"]}
    assert not stages["generate"]["implemented"] and stages["build_scene"]["implemented"]
    assert out["compiled"]["events"]["strike.CONTACT"] == 29
    assert executor.dry_run(request="a dragon flying over Tokyo", reg=reg)["status"] == "unsupported"


def test_cli_generate_dry_run_and_refusal(capsys):
    from onecreations.__main__ import main
    assert main(["generate", PROMPT, "--dry-run"]) == 0
    assert "no process was started" in capsys.readouterr().out
    assert main(["generate", "--spec", str(SHOWCASE_SPEC)]) == 2     # a full run starts from a prompt (D2)
    assert main(["generate"]) == 2
    assert main(["generate", "a dragon flying over Tokyo", "--dry-run"]) == 2
    assert main(["director", "validate", str(SHOWCASE_SPEC)]) == 0


# --- D2: asura_v2 character asset ----------------------------------------------------------------------------------

def test_asura_v2_is_the_default_attacker_and_v1_stays_selectable(reg, spec_dict):
    v2, v1 = reg.get("asura_v2", "character"), reg.get("asura_showcase_v1", "character")
    for k in ("oc_id", "pass_index", "rig", "rig_oc_id", "anchors", "semantic_name"):   # compatible IDs and anchors
        assert v2.data[k] == v1.data[k]
    assert v2.data["material_masks"] == {"skin": 1, "armour": 2, "cloth_harness": 3, "head_details": 4}
    c = compile_shot(plan_to_spec(interpret(PROMPT, reg), reg, "d2_test"), reg)
    assert c.scene_build["attacker_asset"] == "asura_v2" and c.scene_build["material_index_pass"] is True
    asura = next(o for o in c.semantic_objects if o.id == "ASURA")
    assert asura.material_masks == v2.data["material_masks"] and "breastplate" in c.generation.prompt
    # the archived Showcase v1 spec still names v1 and still compiles to the v1 builder without the material pass
    c1 = compile_shot(spec_of(spec_dict), reg)
    assert c1.scene_build["attacker_asset"] == "asura_showcase_v1" and c1.scene_build["material_index_pass"] is False
    assert interpret(PROMPT.replace("horned Asura", "showcase asura"), reg).characters["attacker"] == \
        "asura_showcase_v1"


def test_per_part_masks_from_the_material_index_pass(reg, tmp_path, monkeypatch):
    c = compile_shot(plan_to_spec(interpret(PROMPT, reg), reg, "d2_test"), reg)
    h, w = 8, 10
    obj = np.zeros((49, h, w), np.uint16)
    mat = np.zeros_like(obj)
    obj[:, 2:6, 2:8] = 1                        # the asura
    mat[:, 2:4, 2:8], mat[:, 4:6, 2:8] = 1, 2   # skin above, armour below
    mat[:, 0, :] = 2                            # armour material elsewhere (not the asura) must not leak in

    class B:
        def passes(self):
            return {"object_index": obj, "material_index": mat}
    monkeypatch.setattr("onecreations.blender_bundle.load_bundle", lambda d: B())
    written = []
    monkeypatch.setattr(executor, "_write_png_gray", lambda m, p: written.append((p.name, int(m.sum()))))
    idx = executor.write_masks(c, tmp_path, tmp_path / "masks")
    parts = idx["ASURA"]["parts"]
    assert parts["skin"]["frames"]["29"]["pixels"] == 12 and parts["armour"]["frames"]["29"]["pixels"] == 12
    assert parts["cloth_harness"]["frames"]["29"]["pixels"] == 0
    assert ("asura_armour_f29.png", 12) in written


def test_character_admission_metrics_are_deterministic():
    from tools.admission import character_admission as ca
    blob = np.zeros((40, 40), bool)
    blob[10:30, 10:30] = True
    limbs = blob.copy()
    limbs[10:30, 18:22] = False                 # two separated forms in the same hull
    sb, sl = ca.silhouette(blob), ca.silhouette(limbs)
    assert sb["solidity"] > 0.95 and sl["solidity"] < sb["solidity"] and sl["outline"] > sb["outline"]
    n = np.zeros((40, 40, 3), np.float32)
    n[..., 2] = 1
    assert ca.surface_definition(n, blob)["crease_frac"] == 0.0
    n[:, 20:, :] = (1, 0, 0)                    # a 90 degree crease down the middle
    assert ca.surface_definition(n, blob)["crease_frac"] > 0
