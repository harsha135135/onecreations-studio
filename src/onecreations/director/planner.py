"""DirectorPlan -> ShotSpec: turn the director's decisions into the shot's requirements (still engine-independent)."""

from __future__ import annotations

from onecreations.contracts.director import (ActionSpec, CameraSpec, CharacterSpec, DirectorPlan, EffectEventSpec,
                                             EnvironmentSpec, EventRef, GenerationSettings, GradeSpec, LookSpec,
                                             PropSpec, ShotSpec, TargetRef)
from onecreations.director.registry import Registry

DEFAULT_PROFILE, DEFAULT_GRADE, DEFAULT_SEED = "ltx25_union_768_v1", "showcase_v1", 1000


class PlanError(ValueError):
    pass


def plan_to_spec(plan: DirectorPlan, reg: Registry, shot_id: str = "d1_shot") -> ShotSpec:
    if not plan.supported:
        raise PlanError("the request is not supported by the current library: "
                        + "; ".join(plan.unsupported or ["missing environment, cast, action or look"]))
    names = plan.semantic_names
    chars = [CharacterSpec(id=names[r], role=r, asset=plan.characters[r]) for r in ("attacker", "defender")]
    props = [PropSpec(id=reg.get(w).aliases[0].upper(), asset=w, owner=names[r],
                      mount="weapon_hand" if reg.get(w).data["mount"]["type"] == "rig_bone" else "integrated")
             for r, w in plan.weapons.items()]
    for r in ("attacker", "defender"):
        for i in reg.get(plan.characters[r]).data.get("integrated_props", []):
            props.append(PropSpec(id=reg.get(i).aliases[0].upper(), asset=i, owner=names[r], mount="integrated"))
    def instance(role):                          # action instance ids come from the preset (strike, guard, parry)
        return reg.get(plan.actions[role]).data.get("instance_id", role)
    acts = [ActionSpec(id=instance("attacker"), actor=names["attacker"], preset=plan.actions["attacker"],
                       params=plan.action_params.get("attacker", {}), target=names["defender"]),
            ActionSpec(id=instance("defender"), actor=names["defender"], preset=plan.actions["defender"],
                       params=plan.action_params.get("defender", {}), target=names["attacker"])]
    ce = reg.get(plan.camera)
    dt = ce.data["default_target"]
    camera = CameraSpec(preset=plan.camera, variant=plan.camera_variant,
                        target=TargetRef(anchor=names[dt["anchor_role"]], offset=tuple(dt["offset"])))
    events = [EffectEventSpec(id=v.removesuffix("_v1"), preset=v,
                              trigger=EventRef(action=instance("attacker"), event=reg.get(v).data["trigger_event"]))
              for v in plan.vfx]
    gp = reg.get(DEFAULT_PROFILE)
    # D3(b): a contact action may name an ownership-aligned QC profile; other shots keep the ShotSpec default
    qc_profile = reg.get(plan.actions["attacker"]).data.get("qc_profile")
    return ShotSpec(id=shot_id, description=plan.request, duration_frames=int(gp.data["frames"]),
                    fps=int(gp.data["fps"]), resolution=tuple(gp.data["resolution"]),
                    environment=EnvironmentSpec(asset=plan.environment), characters=chars, props=props,
                    actions=acts, camera=camera, look=LookSpec(preset=plan.look), events=events,
                    generation=GenerationSettings(profile=DEFAULT_PROFILE, seed=DEFAULT_SEED),
                    grade=GradeSpec(preset=DEFAULT_GRADE), **({"qc_profile": qc_profile} if qc_profile else {}))
