"""Build the M3-A shot: the first controlled-cinematic integration shot (finished look + articulation + camera move).

    blender -b --factory-startup --python build_temple_action_scene.py -- --out m3a.blend --spec shot_spec.json

M3-A combines capabilities admitted one at a time: the M2-A temple, the M2-B rigged demon with its original-speed
mace strike (ActionTimeline, same rig space poses and keys), and an M2-C-type camera move (orbit + push-in, fixed
lens), now with a FINISHED look (oc_lookdev: procedural PBR materials, dusk world with light haze, three-point
lighting, AgX) instead of the blockout palette. Geometry, rig, choreography and camera are authored here, so the
depth control, object index, joints and the finished first frame all come from one scene and stay aligned.
- m3a_asura (pass 1) + m3a_mace_head (8, gold: the only gold object) + m3a_mace_shaft (9): the finished demon on the
  M2-B rig (m3a_asura_rig), root fixed at M2-B's position, strike keys from build_temple_strike_scene.
- m3a_defender (pass 2): a static finished ascetic with a trident at the authored impact location, facing the demon.
- Banners (passes 10-12: green / magenta / cyan) on the left colonnade above head height: camera landmarks.
- fx_impact collection (not in the control, the first frame or the reference): a deterministic dust-and-debris burst
  keyed from the ActionTimeline's impact phase start, rendered only as a composite layer (render_layers.py).
--spec writes the scene, choreography + ActionTimeline, the camera move, clearance, the composite layer manifest and
the pre-registered two-axis tracking / gate / classification rules.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import build_temple_camera_scene as camscene  # noqa: E402
import build_temple_shot_scene as temple  # noqa: E402
import build_temple_strike_scene as strike  # noqa: E402
import oc_blender_common as common  # noqa: E402
import oc_import_camera  # noqa: E402
import oc_lookdev as lk  # noqa: E402
from onecreations import hashing  # noqa: E402

FRAMES, FPS, RES = temple.FRAMES, temple.FPS, temple.RES
ROOT_AT = list(strike.ROOT_AT)                       # M2-B's demon position, facing -Y
DEFENDER_AT = [0.95, -4.55, 0.0]                     # beyond the authored contact point, facing the demon (-X)
CAMERA_MOVE = {"target": [-0.85, -4.2, 1.6], "azimuth_deg": [-12.0, 12.0], "radius_m": [8.4, 7.0],
               "height_m": [3.6, 3.3], "ease_linear_mix": 0.5, "yaw_offset_deg": 0.0, "lens_mm": 35.0,
               "sensor_mm": 36.0, "sensor_fit": "AUTO", "clip_start": 0.1, "clip_end": 300.0}
BANNERS = [             # (oc_id, pass, colour, centre, (w, h), yaw deg) on pillar shafts, above head height; chosen
    ("m3a_lm_near", 10, "green", (-3.2, -2.36, 3.25), (0.5, 0.9), 0.0),        # from ray-cast probes of this move
    ("m3a_lm_mid", 11, "magenta", (3.2, 2.64, 3.25), (0.62, 1.2), -12.0),      # right colonnade, 3rd pillar
    ("m3a_lm_far", 12, "cyan", (3.2, 5.14, 3.25), (0.66, 1.4), -14.5),         # right colonnade, rear pillar
]
PARALLAX_LAYERS = ["m3a_lm_near", "m3a_lm_far"]      # mid and far move almost alike under this move (probe: 134 vs
                                                     # 142 px), so only near vs far is order/ratio-checked
BANNER_COLORS = {"green": (0.03, 0.55, 0.05), "magenta": (0.65, 0.03, 0.55), "cyan": (0.02, 0.55, 0.62)}
MIN_CLEARANCE_M = 1.0
STRIKE_FRAMES = strike.DEFAULT_STRIKE_FRAMES         # the ORIGINAL-speed M2-B strike
PROTECT_SPEED_HEAD_WIDTHS = 0.5                      # authored rule for weapon protection (see spec "layers")


# --- finished characters (same rig space as build_temple_strike_scene: feet at origin, facing -Y) --------------

def oval_taper(r_bottom, r_top, depth, loc, mat, y_scale):
    """A V-shaped torso: a tapered cylinder with an oval cross-section, smoothed."""
    o = lk.tapered(r_bottom, r_top, depth, loc, mat, verts=32, subdiv=0)
    o.scale = (1.0, y_scale, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return lk._smooth(o, 2)


def build_finished_asura(m, rig):
    sk, b = strike.skin, strike.bind
    parts = []
    for side, x in (("L", 0.25), ("R", -0.25)):
        parts += [sk(lk.tapered(0.17, 0.14, 0.55, (x, 0.0, 0.275), m["asura_skin"]), f"shin.{side}"),
                  sk(lk.rounded_box((0.26, 0.36, 0.16), (x, -0.05, 0.08), m["leather"], bevel=0.05), f"shin.{side}"),
                  sk(lk.ball(0.12, (x, -0.07, 0.56), m["iron"]), f"shin.{side}"),
                  sk(lk.tapered(0.20, 0.17, 0.55, (x, 0.0, 0.825), m["asura_skin"]), f"thigh.{side}")]
    parts += [sk(lk.tapered(0.62, 0.38, 0.85, (0.0, 0.0, 0.95), m["asura_cloth"], verts=28), "pelvis"),
              sk(lk.torus(0.40, 0.05, (0.0, 0.0, 1.36), m["leather"]), "pelvis"),
              sk(lk.rounded_box((0.18, 0.06, 0.14), (0.0, -0.43, 1.36), m["iron"], bevel=0.03), "pelvis"),
              sk(oval_taper(0.40, 0.53, 0.98, (0.0, 0.0, 1.74), m["asura_skin"], 0.56), "chest"),
              sk(lk.torus(0.30, 0.05, (0.0, -0.02, 2.17), m["iron"]), "chest")]
    for x in (0.2, -0.2):                                         # pectorals and abdominals
        parts.append(sk(lk.ball(0.21, (x, -0.22, 1.98), m["asura_skin"], scale=(1.1, 0.45, 0.75)), "chest"))
        for z in (1.62, 1.47):
            parts.append(sk(lk.ball(0.075, (x * 0.45, -0.205, z), m["asura_skin"], scale=(1.0, 0.45, 0.8)), "chest"))
    for ang in (35, -35):                                         # leather harness straps across the chest
        strap = lk.rounded_box((0.09, 0.05, 1.05), (0.0, -0.27, 1.78), m["leather"], bevel=0.02)
        strap.rotation_euler = (0.0, math.radians(ang), 0.0)
        parts.append(sk(strap, "chest"))
    parts.append(sk(lk.ball(0.08, (0.0, -0.29, 1.80), m["iron"]), "chest"))
    for side, x in (("L", 0.6), ("R", -0.6)):
        parts.append(sk(lk.ball(0.27, (x, 0.0, 2.10), m["iron"], scale=(1.0, 0.95, 0.6)), "chest"))
        parts += [sk(s, "chest") for s in lk.spikes((x, 0.0, 2.14), 0.17, m["iron"], count=4, length=0.13, r=0.035,
                                                     seed=7 if x > 0 else 9)]
    parts += [sk(lk.tapered(0.16, 0.14, 0.16, (0.0, 0.0, 2.25), m["asura_skin"]), "head"),
              sk(lk.ball(0.26, (0.0, 0.0, 2.45), m["asura_skin"], scale=(0.95, 1.0, 1.08)), "head"),
              sk(lk.rounded_box((0.30, 0.22, 0.14), (0.0, -0.07, 2.30), m["asura_skin"], bevel=0.05), "head"),
              sk(lk.tapered(0.05, 0.05, 0.34, (0.0, -0.20, 2.53), m["asura_skin"], rot=(0.0, math.radians(90), 0.0)),
                 "head"),
              sk(lk.ball(0.08, (0.0, 0.06, 2.72), m["hair"]), "head")]
    for x in (0.09, -0.09):
        parts += [sk(lk.ball(0.035, (x, -0.235, 2.48), m["eye"]), "head"),
                  sk(lk.tapered(0.03, 0.0, 0.14, (x, -0.22, 2.36), m["ivory"], verts=12, subdiv=0), "head")]
    for x in (0.14, -0.14):
        parts += [sk(p, "head") for p in lk.horn((x, 0.0, 2.62), (0.55 if x > 0 else -0.55, 0.0, 1.0), 0.45, 0.07,
                                                  m["ivory"])]
    for side, x in (("L", 0.68), ("R", -0.68)):
        parts += [sk(lk.tapered(0.15, 0.12, strike.UPPER_ARM, (x, 0.0, 2.05 - strike.UPPER_ARM / 2), m["asura_skin"]),
                     f"upper_arm.{side}"),
                  sk(lk.tapered(0.13, 0.10, strike.FOREARM, (x, 0.0, 1.55 - strike.FOREARM / 2), m["asura_skin"]),
                     f"forearm.{side}"),
                  sk(lk.tapered(0.14, 0.12, 0.24, (x, 0.0, 1.24), m["iron"]), f"forearm.{side}"),
                  sk(lk.ball(0.125, (x, 0.0, 1.55), m["asura_skin"]), f"forearm.{side}"),
                  sk(lk.ball(0.12, (x, 0.0, 1.0), m["asura_skin"], scale=(1.0, 1.0, 1.15)), f"hand.{side}")]
    body = temple.join(parts, "m3a_asura")
    temple.set_origin(body, (0.0, 0.0, 0.0))
    b(body, rig)
    temple.tag(body, "m3a_asura", 1)
    shaft, head = build_finished_mace(m, rig)
    return body, shaft, head


def build_finished_mace(m, rig):
    """The M3-A mace (shared by M3-B unchanged): iron shaft with leather grip bands (pass 9) and a spiked gold head
    (pass 8, the only gold object), rigidly skinned to the `mace` bone."""
    sk, b = strike.skin, strike.bind
    gx, gz, ml = 0.68, 0.98, strike.MACE_LENGTH
    shaft_parts = [lk.tapered(strike.SHAFT_R, strike.SHAFT_R, ml, (gx, -(ml / 2 - 0.15), gz), m["iron"],
                              rot=(math.radians(90), 0.0, 0.0), verts=12, subdiv=0)]
    for dy in (0.05, -0.12):
        shaft_parts.append(lk.torus(0.058, 0.018, (gx, dy, gz), m["leather"], rot=(math.radians(90), 0.0, 0.0)))
    shaft = temple.join([sk(p, "mace") for p in shaft_parts], "m3a_mace_shaft")
    b(shaft, rig)
    temple.tag(shaft, "m3a_mace_shaft", 9)
    hc = (gx, -ml, gz)
    head_parts = [lk.ball(strike.MACE_HEAD_R, hc, m["gold"])]
    head_parts += lk.spikes(hc, strike.MACE_HEAD_R, m["gold"], count=10, length=0.15, r=0.055)
    head_parts.append(lk.torus(0.12, 0.035, (gx, -ml + strike.MACE_HEAD_R - 0.02, gz), m["gold"],
                               rot=(math.radians(90), 0.0, 0.0)))
    head = temple.join([sk(p, "mace") for p in head_parts], "m3a_mace_head")
    b(head, rig)
    temple.tag(head, "m3a_mace_head", 8)
    return shaft, head


def build_finished_defender(m):
    """Static ascetic (~2.15 m) holding a trident diagonally across the body (defensive stance); faces -Y as built."""
    parts = [lk.tapered(0.15, 0.11, 0.9, (0.13, 0.0, 0.52), m["white_cloth"]),
             lk.tapered(0.15, 0.11, 0.9, (-0.13, 0.0, 0.52), m["white_cloth"]),
             lk.tapered(0.33, 0.26, 0.42, (0.0, 0.0, 0.86), m["white_cloth"], verts=24),
             lk.torus(0.27, 0.035, (0.0, 0.0, 1.06), m["beads"]),
             lk.rounded_box((0.55, 0.32, 0.66), (0.0, 0.0, 1.40), m["ascetic_skin"], bevel=0.12, subdiv=2),
             lk.tapered(0.12, 0.10, 0.12, (0.0, 0.0, 1.78), m["ascetic_skin"]),
             lk.ball(0.21, (0.0, 0.0, 1.98), m["ascetic_skin"], scale=(0.92, 1.0, 1.1)),
             lk.ball(0.13, (0.0, 0.04, 2.22), m["hair"]),
             lk.torus(0.10, 0.04, (0.0, 0.04, 2.16), m["hair"]),
             lk.torus(0.16, 0.025, (0.0, -0.03, 1.66), m["beads"], rot=(math.radians(20), 0.0, 0.0))]
    for x in (0.12, -0.12):
        parts.append(lk.rounded_box((0.14, 0.26, 0.08), (x, -0.04, 0.04), m["ascetic_skin"], bevel=0.03))
    # arms reaching forward to the trident shaft
    parts += [lk.tapered(0.10, 0.08, 0.62, (0.36, -0.18, 1.38), m["ascetic_skin"], rot=(math.radians(55), 0.0, 0.25)),
              lk.tapered(0.10, 0.08, 0.62, (-0.36, -0.20, 1.30), m["ascetic_skin"], rot=(math.radians(60), 0.0, -0.25)),
              lk.ball(0.09, (0.22, -0.46, 1.20), m["ascetic_skin"]), lk.ball(0.09, (-0.24, -0.48, 1.08), m["ascetic_skin"])]
    tilt = math.radians(28)
    c, s = math.cos(tilt), math.sin(tilt)
    tri = [lk.tapered(0.03, 0.03, 2.3, (0.0, -0.5, 1.15), m["iron"], rot=(0.0, tilt, 0.0), verts=10, subdiv=0)]
    top = (1.15 * s, -0.5, 1.15 + 1.15 * c)
    tri.append(lk.tapered(0.02, 0.02, 0.36, top, m["iron"], rot=(0.0, tilt + math.radians(90), 0.0), verts=8, subdiv=0))
    for k in (-1, 0, 1):
        px, pz = top[0] + k * 0.16 * c, top[2] - k * 0.16 * s
        tri.append(lk.tapered(0.022, 0.0, 0.32, (px + 0.14 * s, -0.5, pz + 0.14 * c), m["iron"], rot=(0.0, tilt, 0.0),
                              verts=8, subdiv=0))
    obj = temple.join(parts + tri, "m3a_defender")
    temple.set_origin(obj, (0.0, 0.0, 0.0))
    return obj


# --- deterministic impact effect -----------------------------------------------------------------------------

def impact_point() -> list[float]:
    tip = strike.POSES["contact"]["mace_tip"]
    return [round(ROOT_AT[0] + tip[0], 4), round(ROOT_AT[1] + tip[1], 4), 0.0]


def build_impact_fx(scene, start_frame: int, frames: int = 14, seed: int = 11):
    """Dust puffs + stone chips, keyed per frame from `start_frame` (the ActionTimeline impact start). Hidden from
    every render except the fx layer: the collection is excluded from the view layer here."""
    coll = bpy.data.collections.new("fx_impact")
    scene.collection.children.link(coll)
    dust = bpy.data.materials.new("fx_dust")
    dust.use_nodes = True
    nt = dust.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.46, 0.39, 0.31, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    alpha = bsdf.inputs["Alpha"]                       # one shared dust material; its alpha is keyed over time
    chip_mat = lk.stone("fx_chip", scale=20.0)
    rng = random.Random(seed)
    px, py, _ = impact_point()
    objs = []
    for i in range(30):
        ang = rng.uniform(0, 2 * math.pi)
        vh, vz, r0 = rng.uniform(0.8, 2.0), rng.uniform(0.3, 1.0), rng.uniform(0.12, 0.22)
        bpy.ops.mesh.primitive_ico_sphere_add(radius=1.0, subdivisions=2, location=(px, py, 0.05))
        o = bpy.context.active_object
        o.name = f"fx_dust_{i:02d}"
        o.data.materials.append(dust)
        objs.append((o, "dust", ang, vh, vz, r0))
    for i in range(12):
        ang = rng.uniform(0, 2 * math.pi)
        vh, vz, r0 = rng.uniform(1.0, 2.4), rng.uniform(1.5, 3.0), rng.uniform(0.025, 0.05)
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(px, py, 0.05))
        o = bpy.context.active_object
        o.name = f"fx_chip_{i:02d}"
        o.rotation_euler = (rng.uniform(0, 3), rng.uniform(0, 3), rng.uniform(0, 3))
        o.data.materials.append(chip_mat)
        objs.append((o, "chip", ang, vh, vz, r0))
    for o, *_ in objs:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    span = frames / FPS
    for f in range(scene.frame_start, scene.frame_end + 1):
        t = (f - start_frame) / FPS
        alpha.default_value = 0.0 if t < 0 else max(0.0, 0.7 * (1.0 - t / span))
        alpha.keyframe_insert("default_value", frame=f)
        for o, kind, ang, vh, vz, r0 in objs:
            if t < 0 or t > span:
                o.scale = (0.0, 0.0, 0.0)
            elif kind == "dust":
                drag = 1.0 - math.exp(-6.0 * t)                    # fast initial burst, then slows
                d = vh * drag / 6.0 * 3.0
                o.location = (px + d * math.cos(ang), py + d * math.sin(ang), 0.05 + vz * drag / 2.0)
                s = r0 * (1.0 + 2.5 * drag)
                o.scale = (s, s, s * 0.75)
            else:
                z = max(0.0, 0.05 + vz * t - 4.9 * t * t)
                o.location = (px + vh * t * math.cos(ang), py + vh * t * math.sin(ang), z)
                o.scale = (r0, r0, r0)
            o.keyframe_insert("location", frame=f)
            o.keyframe_insert("scale", frame=f)
    for datablock in [o for o, *_ in objs] + [dust.node_tree]:
        for fc in datablock.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"                  # exact per-frame values, no interpolation overshoot
    bpy.context.view_layer.layer_collection.children["fx_impact"].exclude = True
    return coll


# --- scene ---------------------------------------------------------------------------------------------------

def finish_environment(lmat):
    """Swap the blockout environment's materials for the finished ones (geometry untouched)."""
    swaps = {"m2a_colonnade": lmat["pillar_stone"], "m2a_walls": lmat["stone"], "m2a_rubble": lmat["stone"],
             "m2a_shrine": lmat["shrine_stone"]}
    for name, new in swaps.items():
        o = bpy.data.objects[name]
        for i, slot in enumerate(o.material_slots):
            if slot.material and slot.material.name.startswith("m2a_shrine_dark"):
                o.material_slots[i].material = lmat["shrine_dark"]
            elif slot.material and slot.material.name.startswith("m2a_gold"):
                o.material_slots[i].material = lmat["iron"]          # finial: gold stays unique to the mace head
            else:
                o.material_slots[i].material = new
    floor = bpy.data.objects["m2a_floor"]
    floor.material_slots[0].material = lmat["floor"]


def proxies() -> list[dict]:
    out = [p for p in camscene.proxies() if p["id"] != "actor"]
    out += [{"type": "aabb", "id": "asura", "min": [ROOT_AT[0] - 0.9, ROOT_AT[1] - 1.7, 0.0],
             "max": [ROOT_AT[0] + 1.9, ROOT_AT[1] + 1.0, 3.6]},
            {"type": "aabb", "id": "defender", "min": [DEFENDER_AT[0] - 0.6, DEFENDER_AT[1] - 1.2, 0.0],
             "max": [DEFENDER_AT[0] + 0.6, DEFENDER_AT[1] + 0.6, 2.9]}]
    return out


def build(out_path: str, spec_path: str | None, variant=None) -> dict:
    """Build the shot. `variant` (M3-B on; default None = M3-A exactly) swaps only the characters and annotates the
    spec: an object with build_asura(lmat, rig), build_defender(lmat) -> object, shot (str) and spec_hook(spec) ->
    spec. Environment, banners, look, rig, keys, ActionTimeline, camera move, effect and object ids are unchanged."""
    keys, events, phases = strike.choreography_frames(STRIKE_FRAMES)
    scene = temple.setup_scene()
    m = temple.make_materials()
    lmat = lk.finished_materials()
    cam = temple.add_camera(scene)
    temple.build_environment(m)
    finish_environment(lmat)
    rig = strike.build_rig("m3a_asura_rig")
    (variant.build_asura if variant else build_finished_asura)(lmat, rig)
    reached = strike.key_poses(rig, keys)
    rig.location = ROOT_AT
    defender = (variant.build_defender if variant else build_finished_defender)(lmat)
    defender.location = DEFENDER_AT
    defender.rotation_euler = (0.0, 0.0, math.radians(-90))       # face -X, toward the demon
    temple.tag(defender, "m3a_defender", 2)
    for oc_id, pidx, color, center, size, yaw in BANNERS:
        o = temple.box((size[0], 0.02, size[1]), center, lk.banner(f"lk_banner_{color}", BANNER_COLORS[color]))
        o.rotation_euler = (0.0, 0.0, math.radians(yaw))      # turned toward the camera path (stays clear of the shaft)
        o.name = oc_id
        temple.tag(o, oc_id, pidx)
    lk.cinematic_world(scene)
    lk.haze_volume(scene)
    lk.cinematic_lights(scene)
    lk.cinematic_render_look(scene)
    impact_frame = events["contact"]                              # Blender frame of the impact phase start
    build_impact_fx(scene, impact_frame)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    traj = camscene.camera_samples(CAMERA_MOVE)
    npz = os.path.join(out_dir, "camera_motion.npz")
    traj.save_npz(npz)
    motion = {"schema_version": 1, "id": "m3a_orbit_push_in_v1", "units": "meters",
              "coordinate_system": "blender_z_up", "pose_convention": "camera_to_world",
              "rotation_format": "quaternion_wxyz", "trajectory": "camera_motion.npz",
              "trajectory_sha256": hashing.file_sha256(npz),
              "intrinsics": {"lens_mm": CAMERA_MOVE["lens_mm"], "sensor_width_mm": CAMERA_MOVE["sensor_mm"],
                             "sensor_height_mm": 24.0, "sensor_fit": CAMERA_MOVE["sensor_fit"],
                             "resolution_x": RES[0], "resolution_y": RES[1], "resolution_percentage": 100,
                             "clip_start": CAMERA_MOVE["clip_start"], "clip_end": CAMERA_MOVE["clip_end"]},
              "duration": f"{FRAMES}/{FPS}", "target_bindings": ["m3a_asura.chest", "impact_point"],
              "constraints": {"minimum_clearance_m": MIN_CLEARANCE_M, "preserve_roll": True},
              "provenance": {"source": "authored", "confidence": "verified_in_scene", "scale": "metric_verified",
                             "notes": "M3-A: M2-C-type orbit + push-in around the confrontation, fixed lens"}}
    motion_path = os.path.join(out_dir, "camera_motion.json")
    common.write_json(motion_path, motion)
    oc_import_camera.apply(SimpleNamespace(samples=npz, time_key="t", intrinsics=motion_path, camera_name=cam.name,
                                           frame_start=scene.frame_start, set_scene_camera=True, save=out_path))
    clearance = camscene.clearance_per_frame(scene, cam, FRAMES)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_path))

    eyes = traj.position
    move_info = {"camera_start_m": [round(v, 4) for v in eyes[0]], "camera_end_m": [round(v, 4) for v in eyes[-1]],
                 "chord_m": round(float(np.linalg.norm(eyes[-1] - eyes[0])), 4),
                 "path_m": round(float(np.linalg.norm(np.diff(eyes, axis=0), axis=1).sum()), 4),
                 "peak_speed_m_s": round(float(np.linalg.norm(np.diff(eyes, axis=0), axis=1).max() * FPS), 4),
                 "orbit_deg": CAMERA_MOVE["azimuth_deg"][1] - CAMERA_MOVE["azimuth_deg"][0]}
    timeline = strike.action_timeline(phases, STRIKE_FRAMES)
    timeline.update(id="m3a_mace_slam_v1", actors={"asura": "m3a_asura", "defender": "m3a_defender"})
    timeline["phases"].append({"id": "defender_hold", "kind": "defense", "actor": "defender",
                               "start": "0", "end": strike.src_time(FRAMES)})
    impact_out = impact_frame - scene.frame_start                 # output frame index of the impact beat
    if spec_path:
        common.write_json(os.path.join(os.path.dirname(os.path.abspath(spec_path)), "action_timeline.json"), timeline)
        spec = spec_dict(timeline, reached, keys, events, clearance, move_info, impact_out)
        common.write_json(spec_path, variant.spec_hook(spec) if variant else spec)
    print(f"[oc] {variant.shot if variant else 'M3-A'} temple action scene saved: {out_path} ({move_info})")
    return {"clearance": clearance, "move": move_info}


LANDMARK_GATE = dict(camscene.LANDMARK_GATE)
TRACK_COLORS = {"cyan": "teal"}                     # banner material colour -> finished-look tracker rule
TRAJECTORY_CHECK = dict(camscene.TRAJECTORY_CHECK)


def composite_manifest(impact_out: int) -> dict:
    return {"schema_version": 1, "id": "m3a_layers_v1", "shot": "m3a_action", "layers": [
        {"id": "mace_protect", "kind": "protected_geometry", "objects": ["m3a_mace_head", "m3a_mace_shaft"],
         "render": {"holdout_others": True, "motion_blur_shutter": 0.5, "samples": 64}, "occlusion": "holdout",
         "order": 0, "grade": "per_channel_gain", "ghost_suppression": True,
         "protection": {"track_object": "m3a_mace_head", "authored_speed_widths": PROTECT_SPEED_HEAD_WIDTHS,
                        "dilate_frames": 1, "raw_retention_below": 0.5}},
        {"id": "impact_dust", "kind": "effect", "collections": ["fx_impact"],
         "render": {"holdout_others": True, "motion_blur_shutter": 0.5, "samples": 64}, "occlusion": "holdout",
         "order": 1, "trigger": {"timeline": "m3a_mace_slam_v1", "phase": "impact", "edge": "start"},
         "duration_frames": 14}]}


def spec_dict(timeline, reached, keys, events, clearance, move_info, impact_out) -> dict:
    return {
        "shot": "m3a_action",
        "purpose": ("M3-A: first controlled-cinematic integration shot. The M2-B strike (original speed) on a finished "
                    "demon, a static finished ascetic at the impact location, an M2-C-type camera move, a finished "
                    "procedural look; raw LTX + a deterministic hybrid layer for the weapon + one ActionTimeline-"
                    "triggered impact effect"),
        "frames": FRAMES, "fps": FPS, "resolution": list(RES), "camera": temple.CAMERA,
        "scene": dict(temple.scene_spec(), look="oc_lookdev finished (procedural PBR, dusk world, bounded haze 0.006, "
                                                "AgX High Contrast, exposure -0.3)",
                      root_at=ROOT_AT, defender_at=DEFENDER_AT, defender_yaw_deg=-90,
                      banners=[{"oc_id": b[0], "pass_index": b[1], "color": b[2], "center": b[3], "size": b[4],
                                "yaw_deg": b[5]} for b in BANNERS],
                      impact_point=impact_point()),
        "choreography": {
            "m3a_asura": {"rig": "m3a_asura_rig", "root_at": ROOT_AT, "source": "build_temple_strike_scene POSES/KEYS "
                          "(M2-B, --strike-frames 6)", "reached_rig_space": reached,
                          "keys": {str(f): {"pose": p, "interpolation": i, "easing": e}
                                   for f, (p, i, e) in sorted(keys.items())},
                          "events_blender_frame": events},
            "m3a_defender": {"motion": "static (defensive stance)", "at": DEFENDER_AT},
            "action_timeline": timeline,
            "camera_move": dict(CAMERA_MOVE, **move_info),
            "camera_motion": {"manifest": "camera_motion.json", "samples": "camera_motion.npz"},
            "impact_output_frame": impact_out,
        },
        "camera_clearance": clearance,
        "clearance_proxies": proxies(),
        "layers": composite_manifest(impact_out),
        "tracking": {
            "subjects": dict({
                "m3a_asura": {"color": "crimson", "role": "primary", "ignore_occluders": ["m3a_mace_head", "m3a_mace_shaft"],
                              "checks": {"position": {"tol_px": 32, "area_tol": 0.25}}},
                "m3a_mace_head": {"color": "gold_deep", "role": "primary", "ignore_occluders": ["m3a_mace_shaft"],
                                  "gate": {"min_height_cells": 0.6, "min_width_cells": 0.6, "min_area_cells": 0.25,
                                           "min_excursion_cells": 2.0, "contrast_frames": "events",
                                           "require_visible_all_frames": True},
                                  "checks": {"timing": {"tol_frames": 2, "stop_px": 4, "min_excursion_frac": 0.5,
                                                        "min_detect_frac": 0.9, "min_dx_px": 32}}}},
                **{b[0]: {"color": TRACK_COLORS.get(b[2], b[2]), "role": "primary", "gate": LANDMARK_GATE,
                          "checks": {"trajectory": TRAJECTORY_CHECK}} for b in BANNERS},
                m3a_defender={"color": "blue", "role": "secondary", "checks": {"report_only": {}}}),
            "ground": ["m2a_floor"],
            "static_structures": [],
            "gate": {"min_height_cells": 2.0, "min_area_cells": 2.0, "min_width_cells": 1.5,
                     "min_control_contrast": 0.08, "require_in_frame": True},
            "parallax": {"layers": PARALLAX_LAYERS, "min_gt_separation": 1.25, "ratio_tol": 1.35},
            "joints": {"rig": "m3a_asura_rig", "weapon_bone": "mace", "weapon_object": "m3a_mace_head",
                       "stationary_bones": strike.STATIONARY_BONES, "max_projection_err_px": 3.0,
                       "max_stationary_m": 0.001},
            "timeline": {"apex_after_phase": "windup", "contact_after_phase": "strike", "tol_frames": 1},
            "camera_contract": {"samples": "camera_motion.npz", "max_position_err_m": 0.001, "max_angle_err_deg": 0.05},
            "clearance": {"min_m": MIN_CLEARANCE_M},
            "notes": ("finished look: colour rules are validated on the finished Blender reference before the run; "
                      "static-structure drift omitted (moving camera). The demon's framing uses `position` (displacement "
                      "from frame 0 + relative area within 25%) only: on the finished reference the red-mask area does "
                      "not reproduce the GT push-in growth (x1.11 vs x1.27, armour/harness/arm occlusion), so `approach` "
                      "was removed before any generation"),
        },
        "classification": {
            "control_pass": ("timing (mace apex/contact within 2 frames, excursion >= 50%) AND position + approach "
                             "(demon framing) AND every landmark trajectory + parallax (M2-C rules) followed on the RAW "
                             "LTX output, AND visually: the authored action stays readable, the weapon arm visibly "
                             "articulates through every phase, the impact lands on the authored beat, the camera "
                             "progression is coherent and the environment stays coherent"),
            "control_partial": ("the action is readable and timed but a non-critical control element degrades "
                                "(a landmark, framing, parallax magnitude), or articulation is weakened"),
            "control_fail": "the action, timing or camera becomes unusable or contradicted",
            "appearance_pass": ("visual, vs the closest controlled blockout baselines (ltx25-m2b-strike for the action, "
                                "ltx25-m2c-camera for the camera move) at matched beats: materially more finished; the "
                                "characters no longer read primarily as primitive geometry; temple material/lighting "
                                "richness materially improved; the improved look persists through most of the shot "
                                "(guard, wind-up, apex, fast swing, impact, hold, recovery, final frame); temporally "
                                "coherent enough to be useful"),
            "appearance_partial": ("appearance improves but collapses toward blockout during motion, or identity/"
                                   "material consistency drifts, or the transformation is weak"),
            "appearance_fail": "appearance not materially improved, or improvement destroys structure",
            "hybrid_usable": ("the protected mace is present, solid, on the authored path, attached to the generated "
                              "hand (projected grip within 12 px of generated crimson hand pixels) and correctly "
                              "occluded in every protected frame, with no obvious halo or double image. On-path: per "
                              "protected frame, the composite's tracked weapon centroid is within (dry-run error + 3 px) "
                              "of the blur-matched reference's, where the dry run composites the same layer over the "
                              "blur-matched reference itself (the tool's own error on the authored truth, up to 5.7 px "
                              "at the fastest frame from thresholding a blur streak). Centroid vs the sharp object-index "
                              "GT is report-only (motion blur biases it by up to 6.4 px)"),
            "full_pass": "CONTROL PASS + APPEARANCE PASS + hybrid usable through the critical interval",
            "owner_playback": "not required for classification; recorded separately if given",
            "retry": ("at most one evidence-driven retry, only if the integration class is not FULL PASS and one "
                      "dominant, fixable cause is identified; none after a FULL PASS"),
        },
        "blender": common.blender_version(),
    }


def main() -> None:
    p = argparse.ArgumentParser(prog="build_temple_action_scene")
    p.add_argument("--out", required=True)
    p.add_argument("--spec", default=None)
    a = p.parse_args(common.script_args())
    build(a.out, a.spec)


if __name__ == "__main__":
    main()
