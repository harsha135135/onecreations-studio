"""Build the M2-B shot: the M2-A temple with a rigged humanoid proxy performing ONE articulated mace strike.

    blender -b --factory-startup --python build_temple_strike_scene.py -- --out m2b.blend --spec shot_spec.json \
        [--strike-frames 6]

M2-B changes one axis from M2-A: rigid translation -> articulation. Same temple, camera (static), 512x320, 49 frames
@ 24 fps. The actor's root and legs are never keyed: no translation, so any movement in the result is articulation.
- m2b_asura (pass 1): the M2-A crimson proxy as ONE mesh, rigidly skinned (each primitive weighted 1.0 to one bone)
  to m2b_asura_rig (tagged, so oc_export writes its bones to joints.npz). Pauldrons are iron and horns ivory, so the
  mace head is the only gold object in the scene (the shrine finial is stone here).
- m2b_mace_head (pass 8, gold sphere) and m2b_mace_shaft (pass 9, iron) are skinned to the `mace` bone, whose tail is
  the head's centre (3D ground truth for the weapon comes straight from joints.npz).
- Choreography (Blender frames): guard 1-8 -> wind-up 8-24 (mace up and back over the weapon-side shoulder) -> APEX 24
  -> strike 24-30 (ease-in, then constant speed: a forward-downward chop on the weapon side, away from the torso so the
  depth control carries it against the background) -> CONTACT 30 (head on the floor) -> impact hold 30-35 ->
  recovery 35-49 (back to a low guard, below the apex). Poses are given as grip / mace targets in rig space and solved
  with an analytic two-bone IK into FK quaternion keys.
- --strike-frames N (default 6) sets the apex -> contact duration; the impact hold still ends at frame 35, so the guard,
  wind-up, apex and recovery are unchanged (the M2-B retry used 9: the same strike stretched x1.5 in time, mid key on frame 28.5).
- The static ascetic m2a_shiva and the M2-A environment are built by build_temple_shot_scene.py (same oc_ids).
--spec writes the scene, the choreography (incl. an ActionTimeline, also written as action_timeline.json next to the
spec) and the pre-registered tracking / gate / classification rules used by tools/admission/control_diagnostic.py.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
from mathutils import Euler, Matrix, Vector  # noqa: E402

import build_temple_shot_scene as temple  # noqa: E402
import oc_blender_common as common  # noqa: E402
from onecreations.timebase import format_time  # noqa: E402

FRAMES, FPS, RES = temple.FRAMES, temple.FPS, temple.RES
ROOT_AT = [-1.8, -4.0, 0.0]                 # feet centre, ~6 m from the camera, left of centre (shiva stays visible)
WEAPON_SIDE = "L"                           # actor's left = +X (Blender convention for a character facing -Y)
ACTOR_COLORS = {"asura_skin": [0.62, 0.06, 0.05], "asura_cloth": [0.45, 0.04, 0.04], "iron": [0.25, 0.25, 0.27],
                "ivory": [0.85, 0.80, 0.65], "gold": [0.85, 0.62, 0.20]}
MACE_LENGTH, MACE_HEAD_R, SHAFT_R = 1.15, 0.34, 0.05
UPPER_ARM, FOREARM, HAND = 0.5, 0.45, 0.12

# (name, head, tail, parent, connected) in rig space: feet centre at the origin, facing -Y.
BONES = [
    ("root", (0, 0, 0), (0, 0, 0.4), None, False),
    ("pelvis", (0, 0, 1.0), (0, 0, 1.25), "root", False),
    ("spine", (0, 0, 1.25), (0, 0, 1.6), "pelvis", True),
    ("chest", (0, 0, 1.6), (0, 0, 2.2), "spine", True),
    ("head", (0, 0, 2.2), (0, 0, 2.7), "chest", True),
    ("upper_arm.L", (0.68, 0, 2.05), (0.68, 0, 1.55), "chest", False),
    ("forearm.L", (0.68, 0, 1.55), (0.68, 0, 1.10), "upper_arm.L", True),
    ("hand.L", (0.68, 0, 1.10), (0.68, 0, 0.98), "forearm.L", True),
    ("mace", (0.68, 0, 0.98), (0.68, -MACE_LENGTH, 0.98), "hand.L", True),
    ("upper_arm.R", (-0.68, 0, 2.05), (-0.68, 0, 1.55), "chest", False),
    ("forearm.R", (-0.68, 0, 1.55), (-0.68, 0, 1.10), "upper_arm.R", True),
    ("hand.R", (-0.68, 0, 1.10), (-0.68, 0, 0.98), "forearm.R", True),
    ("thigh.L", (0.25, 0, 1.1), (0.25, 0, 0.55), "pelvis", False),
    ("shin.L", (0.25, 0, 0.55), (0.25, 0, 0.0), "thigh.L", True),
    ("thigh.R", (-0.25, 0, 1.1), (-0.25, 0, 0.55), "pelvis", False),
    ("shin.R", (-0.25, 0, 0.55), (-0.25, 0, 0.0), "thigh.R", True),
]
STATIONARY_BONES = ["root", "pelvis", "thigh.L", "thigh.R", "shin.L", "shin.R"]

# Key poses in rig space. chest = (lean deg, + toward the camera; twist deg about Z). Weapon: `grip` (hand tail) or
# `mace_tip` (head centre) plus the mace direction. off_grip = the non-weapon hand. Elbow poles fix the IK plane.
# The apex pose is the top of the arc (mace near vertical), so the head's highest point is the authored apex frame and
# stays inside the top edge; the recovery swings the mace outward and up, never lower on screen than the contact.
POSES = {
    "guard": {"chest": [0, 0], "grip": [0.60, -0.40, 1.15], "mace_dir": [0.57, -0.32, 0.76],
              "off_grip": [-0.62, -0.25, 1.20]},
    "apex": {"chest": [-8, 10], "grip": [0.95, 0.05, 1.85], "mace_dir": [0.25, 0.10, 0.96],
             "off_grip": [-0.55, -0.50, 1.75]},
    "mid": {"chest": [4, -2], "grip": [0.95, -0.45, 1.75], "mace_dir": [0.45, -0.88, 0.13],
            "off_grip": [-0.62, -0.10, 1.45]},
    "contact": {"chest": [12, -8], "mace_tip": [1.45, -0.30, MACE_HEAD_R], "mace_dir": [0.35, -0.15, -0.92],
                "off_grip": [-0.70, 0.20, 1.30]},
    "recovery": {"chest": [3, 0], "grip": [0.75, -0.15, 1.30], "mace_dir": [0.55, -0.20, 0.60],
                 "off_grip": [-0.62, -0.20, 1.15]},
}
POLES = {"L": [0.7, 0.2, -0.7], "R": [-0.7, 0.25, -0.6]}
APEX_FRAME, HOLD_END, DEFAULT_STRIKE_FRAMES = 24, 35, 6


def choreography_frames(strike_frames: int = DEFAULT_STRIKE_FRAMES):
    """(keys, events, phases) in Blender frames. keys: frame -> (pose, interpolation of the segment that starts there,
    easing). The strike runs from the apex (24) to the contact; the mid key splits it (ease-in, then constant speed)."""
    contact = APEX_FRAME + strike_frames
    if not 2 <= strike_frames <= HOLD_END - APEX_FRAME - 2:
        raise ValueError(f"strike_frames {strike_frames} leaves no impact hold before frame {HOLD_END}")
    half = Fraction(strike_frames, 2)              # the mid key may sit on a half frame: a pure time stretch of the strike
    mid = APEX_FRAME + (int(half) if half.denominator == 1 else float(half))
    keys = {1: ("guard", "BEZIER", "AUTO"), 8: ("guard", "BEZIER", "AUTO"), APEX_FRAME: ("apex", "QUAD", "EASE_IN"),
            mid: ("mid", "LINEAR", "AUTO"), contact: ("contact", "LINEAR", "AUTO"),
            HOLD_END: ("contact", "BEZIER", "AUTO"), 49: ("recovery", "BEZIER", "AUTO")}
    events = {"apex": APEX_FRAME, "contact": contact}   # output frame index = Blender frame - 1
    phases = [("guard", "idle", 1, 8), ("windup", "other", 8, APEX_FRAME), ("strike", "strike", APEX_FRAME, contact),
              ("impact", "impact", contact, HOLD_END), ("recovery", "recovery", HOLD_END, 49)]
    return keys, events, phases


def src_time(frame: int) -> str:
    return format_time(Fraction(frame - 1, FPS))


def action_timeline(phases, strike_frames: int = DEFAULT_STRIKE_FRAMES) -> dict:
    version = "1.0.0" if strike_frames == DEFAULT_STRIKE_FRAMES else f"1.0.0-strike{strike_frames}f"
    return {"schema_version": 1, "id": "m2b_mace_strike_v1", "version": version,
            "duration": format_time(Fraction(FRAMES, FPS)), "actors": {"asura": "m2b_asura"},
            "phases": [{"id": i, "kind": k, "actor": "asura", "start": src_time(a), "end": src_time(b)}
                       for i, k, a, b in phases],
            "contacts": []}


# --- actor geometry ------------------------------------------------------------------------------------------

def skin(obj, bone: str):
    vg = obj.vertex_groups.new(name=bone)
    vg.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
    return obj


def bind(obj, rig) -> None:
    """Rigid skinning: an Armature modifier plus object parenting while the rig is still at the origin."""
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    obj.parent = rig


def build_actor(m, rig):
    cyl, sph, cone, box = temple.cylinder, temple.sphere, temple.cone, temple.box
    parts = []
    for side, x in (("L", 0.25), ("R", -0.25)):
        parts.append(skin(cyl(0.17, 0.55, (x, 0.0, 0.275), m["asura_skin"]), f"shin.{side}"))
        parts.append(skin(cyl(0.17, 0.55, (x, 0.0, 0.825), m["asura_skin"]), f"thigh.{side}"))
    parts.append(skin(cone(0.62, 0.36, 0.85, (0.0, 0.0, 0.95), m["asura_cloth"]), "pelvis"))
    parts.append(skin(box((0.95, 0.52, 0.95), (0.0, 0.0, 1.75), m["asura_skin"]), "chest"))
    for side, x in (("L", 0.68), ("R", -0.68)):
        parts.append(skin(sph(0.24, (x * 0.88, 0.0, 2.12), m["iron"]), "chest"))
        parts.append(skin(cyl(0.13, UPPER_ARM, (x, 0.0, 2.05 - UPPER_ARM / 2), m["asura_skin"]), f"upper_arm.{side}"))
        parts.append(skin(cyl(0.12, FOREARM, (x, 0.0, 1.55 - FOREARM / 2), m["asura_skin"]), f"forearm.{side}"))
        parts.append(skin(sph(0.12, (x, 0.0, 1.0), m["asura_skin"]), f"hand.{side}"))
    parts.append(skin(sph(0.26, (0.0, 0.0, 2.42), m["asura_skin"]), "head"))
    parts.append(skin(cone(0.08, 0.0, 0.32, (-0.15, 0.0, 2.72), m["ivory"], rotation=(0, math.radians(-15), 0)), "head"))
    parts.append(skin(cone(0.08, 0.0, 0.32, (0.15, 0.0, 2.72), m["ivory"], rotation=(0, math.radians(15), 0)), "head"))
    body = temple.join(parts, "m2b_asura")
    temple.set_origin(body, (0.0, 0.0, 0.0))
    bind(body, rig)
    temple.tag(body, "m2b_asura", 1)

    gx, gz = 0.68, 0.98
    shaft = skin(cyl(SHAFT_R, MACE_LENGTH, (gx, -(MACE_LENGTH / 2 - 0.15), gz), m["iron"],
                     rotation=(math.radians(90), 0, 0), vertices=12), "mace")
    shaft.name = "m2b_mace_shaft"
    bind(shaft, rig)
    temple.tag(shaft, "m2b_mace_shaft", 9)
    head = skin(sph(MACE_HEAD_R, (gx, -MACE_LENGTH, gz), m["gold"]), "mace")
    head.name = "m2b_mace_head"
    bind(head, rig)
    temple.tag(head, "m2b_mace_head", 8)
    return body, shaft, head


def build_rig():
    arm = bpy.data.armatures.new("m2b_asura_rig")
    rig = bpy.data.objects.new("m2b_asura_rig", arm)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    eb = {}
    for name, head, tail, parent, connected in BONES:
        b = arm.edit_bones.new(name)
        b.head, b.tail, b.roll = Vector(head), Vector(tail), 0.0
        if parent:
            b.parent = eb[parent]
            b.use_connect = connected
        b.use_deform = name != "root"
        eb[name] = b
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
    temple.tag(rig, "m2b_asura_rig")
    return rig


# --- pose solving (rig space) --------------------------------------------------------------------------------

def two_bone_ik(s: Vector, g: Vector, l1: float, l2: float, pole: Vector) -> Vector:
    """Elbow position for a shoulder s reaching g with segment lengths l1, l2, bending toward `pole`."""
    d_vec = g - s
    d = min(max(d_vec.length, abs(l1 - l2) + 1e-4), l1 + l2 - 1e-4)
    if d_vec.length > l1 + l2:
        raise ValueError(f"IK target {tuple(g)} out of reach ({d_vec.length:.3f} > {l1 + l2:.3f} m)")
    u = d_vec.normalized()
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    h = math.sqrt(max(l1 * l1 - a * a, 0.0))
    v = pole - u * pole.dot(u)
    v.normalize()
    return s + u * a + v * h


def solve_pose(rig, pose: dict) -> dict[str, Matrix]:
    """Rig-space pose matrices for every bone (hierarchy order); unlisted bones follow their parent rigidly."""
    rest = {b.name: b.matrix_local.copy() for b in rig.data.bones}
    parent = {name: par for name, _, _, par, _ in BONES}
    P: dict[str, Matrix] = {}

    def follow(name):
        par = parent[name]
        return rest[name].copy() if par is None else P[par] @ rest[par].inverted() @ rest[name]

    def aim(name, head: Vector, direction: Vector) -> Matrix:
        rot = rest[name].to_3x3()
        q = rot.col[1].rotation_difference(direction.normalized())
        out = (q.to_matrix() @ rot).to_4x4()
        out.translation = head
        return out

    lean, twist = pose["chest"]
    side_dirs = {}
    for name, *_ in BONES:
        base = follow(name)
        if name == "chest":
            h = base.translation.copy()
            r = Euler((math.radians(lean), 0.0, math.radians(twist)), "XYZ").to_matrix().to_4x4()
            P[name] = Matrix.Translation(h) @ r @ Matrix.Translation(-h) @ base
        elif name.startswith("upper_arm."):
            side = name[-1]
            s = base.translation.copy()
            if side == WEAPON_SIDE:
                mdir = Vector(pose["mace_dir"]).normalized()
                grip = (Vector(pose["grip"]) if "grip" in pose
                        else Vector(pose["mace_tip"]) - mdir * MACE_LENGTH)
            else:
                mdir, grip = None, Vector(pose["off_grip"])
            elbow = two_bone_ik(s, grip, UPPER_ARM, FOREARM + HAND, Vector(POLES[side]))
            side_dirs[side] = (elbow, grip, mdir)
            P[name] = aim(name, s, elbow - s)
        elif name.startswith("forearm."):
            elbow, grip, _ = side_dirs[name[-1]]
            P[name] = aim(name, elbow, grip - elbow)
        elif name == "mace":
            _, grip, mdir = side_dirs[WEAPON_SIDE]
            P[name] = aim(name, base.translation.copy(), mdir)
        else:
            P[name] = base
    return P


def key_poses(rig, keys: dict) -> dict:
    """Insert quaternion keys; returns per-pose rig-space joint targets actually reached (for the spec)."""
    parent = {name: par for name, _, _, par, _ in BONES}
    rest = {b.name: b.matrix_local.copy() for b in rig.data.bones}
    prev_q = {}
    reached = {}
    for frame, (pose_name, _, _) in sorted(keys.items()):
        P = solve_pose(rig, POSES[pose_name])
        for name, *_ in BONES:
            par = parent[name]
            base = rest[name] if par is None else P[par] @ rest[par].inverted() @ rest[name]
            local = base.inverted() @ P[name]
            if local.translation.length > 1e-5:
                raise RuntimeError(f"{name}: pose would move a bone head ({local.translation.length:.2e} m)")
            q = local.to_quaternion()
            if name in prev_q and q.dot(prev_q[name]) < 0.0:
                q.negate()
            prev_q[name] = q
            pb = rig.pose.bones[name]
            pb.rotation_quaternion = q
            pb.keyframe_insert("rotation_quaternion", frame=frame)
        tail = P["mace"] @ Vector((0.0, rig.data.bones["mace"].length, 0.0))
        reached[pose_name] = {"mace_head_centre": [round(v, 4) for v in tail],
                              "grip": [round(v, 4) for v in P["mace"].translation]}
    for fc in rig.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            _, interp, easing = keys[min(keys, key=lambda f: abs(f - kp.co[0]))]
            kp.interpolation = interp
            kp.easing = easing
    return reached


def build(out_path: str, spec_path: str | None, strike_frames: int = DEFAULT_STRIKE_FRAMES) -> None:
    keys, events, phases = choreography_frames(strike_frames)
    scene = temple.setup_scene()
    m = temple.make_materials()
    m.update({k: temple.flat_material(f"m2b_{k}", v) for k, v in ACTOR_COLORS.items()})
    m["gold"].node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 0.6
    temple.add_camera(scene)
    temple.build_environment(m, finial=m["stone_b"])
    temple.add_shiva(m)
    rig = build_rig()
    build_actor(m, rig)
    reached = key_poses(rig, keys)
    rig.location = ROOT_AT
    temple.add_sun(scene)

    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_path))
    if spec_path:
        timeline = action_timeline(phases, strike_frames)
        common.write_json(os.path.join(os.path.dirname(os.path.abspath(spec_path)), "action_timeline.json"), timeline)
        variant = ({} if strike_frames == DEFAULT_STRIKE_FRAMES else
                   {"variant": f"strike {strike_frames} frames (default {DEFAULT_STRIKE_FRAMES}); everything else as M2-B"})
        common.write_json(spec_path, {
            **variant,
            "shot": "m2b_strike",
            "purpose": ("M2-B: M2-A's representative environment and static camera; ONE articulated action (a mace "
                        "strike) by a rigged humanoid proxy whose root and legs never move (rigid -> articulated)"),
            "frames": FRAMES, "fps": FPS, "resolution": list(RES), "camera": temple.CAMERA,
            "scene": dict(temple.scene_spec(), shrine_finial="stone_b (gold is unique to the mace head)",
                          actor_colors=ACTOR_COLORS),
            "choreography": {
                "m2b_asura": {"rig": "m2b_asura_rig", "root_at": ROOT_AT, "root_motion": "none (root and legs unkeyed)",
                              "weapon_side": f"{WEAPON_SIDE} (+X)", "bones": [b[0] for b in BONES],
                              "mace": {"length": MACE_LENGTH, "head_radius": MACE_HEAD_R, "shaft_radius": SHAFT_R},
                              "arm_lengths": {"upper": UPPER_ARM, "forearm": FOREARM, "hand": HAND},
                              "poses": POSES, "poles": POLES, "reached_rig_space": reached,
                              "keys": {str(f): {"pose": p, "interpolation": i, "easing": e}
                                       for f, (p, i, e) in sorted(keys.items())},
                              "events_blender_frame": events},
                "action_timeline": timeline,
            },
            "tracking": {
                "subjects": {
                    "m2b_asura": {"color": "red", "role": "primary",
                                  "ignore_occluders": ["m2b_mace_head", "m2b_mace_shaft"],
                                  "checks": {"position": {"tol_px": 32, "area_tol": 0.25}}},
                    "m2b_mace_head": {"color": "gold", "role": "primary", "ignore_occluders": ["m2b_mace_shaft"],
                                      "gate": {"min_height_cells": 0.75, "min_width_cells": 0.75,
                                               "min_area_cells": 0.4, "min_excursion_cells": 2.0,
                                               "contrast_frames": "events", "require_visible_all_frames": True},
                                      "checks": {"timing": {"tol_frames": 2, "stop_px": 4,
                                                            "min_excursion_frac": 0.5, "min_detect_frac": 0.9,
                                                            "min_dx_px": 32}}},
                    "m2a_shiva": {"color": "blue", "role": "secondary", "checks": {"report_only": {}}},
                },
                "ground": ["m2a_floor"],
                "static_structures": ["m2a_colonnade", "m2a_shrine", "m2a_walls"],
                "gate": {"min_height_cells": 2.0, "min_area_cells": 2.0, "min_width_cells": 1.5,
                         "min_control_contrast": 0.08, "require_in_frame": True},
                "joints": {"rig": "m2b_asura_rig", "weapon_bone": "mace", "weapon_object": "m2b_mace_head",
                           "stationary_bones": STATIONARY_BONES, "max_projection_err_px": 3.0,
                           "max_stationary_m": 0.001},
                "timeline": {"apex_after_phase": "windup", "contact_after_phase": "strike", "tol_frames": 1},
                "notes": ("static-structure drift is report-only; the mace head's control contrast is gated at the GT "
                          "apex and contact only and reported per frame (low while it passes in front of the torso)"),
            },
            "classification": {
                "pass": ("timing (m2b_mace_head) and position (m2b_asura) followed, AND coherent weapon-side arm "
                         "articulation visible through guard -> wind-up/apex -> strike/contact -> recovery, AND the "
                         "strike reads visually"),
                "articulation_visual_criterion": (
                    "owner, 2026-10-03: the weapon arm visibly changes pose through every phase; NOT acceptable: the "
                    "mace moving independently of the arm, the limb materially smearing or ghosting, or the whole "
                    "actor translating. Judged on the checkpoint and event contact sheets; no extra tracker"),
                "partial": ("the weapon moves the right way but the timing or excursion is off, or the limb or weapon "
                            "is materially smeared or ghosted"),
                "fail": "the weapon motion is absent or contradicted, or the actor is unusable",
                "owner_playback": "not required for classification; recorded separately if given",
                "retry": "at most one evidence-driven retry, only after PARTIAL or FAIL; none after a PASS",
            },
            "blender": common.blender_version(),
        })
    print(f"[oc] M2-B temple strike scene saved: {out_path}")


def main() -> None:
    p = argparse.ArgumentParser(prog="build_temple_strike_scene")
    p.add_argument("--out", required=True)
    p.add_argument("--spec", default=None)
    p.add_argument("--strike-frames", type=int, default=DEFAULT_STRIKE_FRAMES)
    a = p.parse_args(common.script_args())
    build(a.out, a.spec, a.strike_frames)


if __name__ == "__main__":
    main()
