"""Build the M2-C shot: the M2-A temple and rigid humanoid proxy (static) under ONE authored camera move.

    blender -b --factory-startup --python build_temple_camera_scene.py -- --out m2c.blend --spec shot_spec.json

M2-C changes one axis from the proven baseline: static camera -> authored moving camera. 512x320, 49 frames @ 24 fps.
- m2c_asura (pass 1): the M2-A crimson proxy (same geometry and materials), STATIC (no keys at all), so all image
  motion of the scene comes from the camera. No articulation, weapon motion, contact, physics or VFX.
- Camera: a moderate orbit (24 deg) + push-in (7.5 -> 6.0 m) around the actor from a moderately raised position
  (3.6 -> 3.3 m, ~15-16 deg down, so the shrine stays visible above the actor's head), fixed 35 mm lens. Each frame
  looks at the actor's chest with a constant 12 deg yaw framing offset, so the actor stays at a fixed screen position
  (right third) while the background sweeps across the left of the frame. The move is authored here with geometry.conventions.look_at, stored as a
  CameraTrajectory (camera_motion.npz) plus a CameraMotion manifest (camera_motion.json), and keyed onto OC_Camera
  by the Session A importer (oc_import_camera.apply), one sample per frame.
- Parallax landmarks: flat cloth banners in colours absent from the M2-A scene, at three depths, chosen from per-frame
  ray-cast visibility probes of the authored move (visible in every frame, never behind the actor): banners on the
  shafts of the left colonnade, NEAR green on the front pillar (~9.2 m), MID magenta on the second (~11.5 m), FAR cyan
  on the rear pillar (~16.4 m). Each is a separate object (own pass index) for ground truth and is tracked by colour.
  The actor stands right of centre (x = +2) so the whole left colonnade stays clear of it.
  The static ascetic m2a_shiva (blue) is report-only: it passes behind the actor (occlusion/reveal ordering).
--spec writes the scene, the camera move, clearance (exact closest-point distance to every tagged mesh, per frame),
proxies for camera.retarget.clearance_report, and the pre-registered tracking / gate / classification rules.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import build_temple_shot_scene as temple  # noqa: E402
import oc_blender_common as common  # noqa: E402
import oc_import_camera  # noqa: E402
from onecreations import hashing  # noqa: E402
from onecreations.camera.trajectory import CameraTrajectory  # noqa: E402
from onecreations.geometry import conventions  # noqa: E402

FRAMES, FPS, RES = temple.FRAMES, temple.FPS, temple.RES
ACTOR_AT = [2.0, -3.5, 0.0]                  # right of centre: the left colonnade stays clear of the actor
# Orbit + push-in around the actor's chest. azimuth 0 = straight in front (-Y side); radius/height are horizontal
# distance and camera height; ease = mix of linear and cosine ease-in/out; yaw_offset turns the view left so the actor
# sits right of centre (fixed). All values are authored before any generation.
CAMERA_MOVE = {"target": [2.0, -3.5, 1.55], "azimuth_deg": [-13.0, 11.0], "radius_m": [7.5, 6.0],
               "height_m": [3.6, 3.3], "ease_linear_mix": 0.5, "yaw_offset_deg": 12.0, "lens_mm": 35.0,
               "sensor_mm": 36.0, "sensor_fit": "AUTO", "clip_start": 0.1, "clip_end": 300.0}
BANNER_COLORS = {"green": [0.03, 0.55, 0.05], "magenta": [0.65, 0.03, 0.55], "cyan": [0.02, 0.55, 0.62]}
# (oc_id, pass index, colour, centre, (width, height), facing) — facing -Y unless noted; chosen from visibility probes
BANNERS: list[tuple] = [                                      # on the left colonnade's pillar shafts (front faces)
    ("m2c_lm_near", 10, "green", (-3.2, -2.36, 2.6), (0.5, 1.3), "-Y"),      # pillar (-3.2, -2.0), ~9.2 m
    ("m2c_lm_mid", 11, "magenta", (-3.2, 0.14, 2.6), (0.6, 1.5), "-Y"),      # pillar (-3.2, +0.5), ~11.5 m
    ("m2c_lm_far", 12, "cyan", (-3.2, 5.14, 2.6), (0.62, 1.6), "-Y"),        # pillar (-3.2, +5.5), ~16.4 m
]
LANDMARK_LAYERS = ["m2c_lm_near", "m2c_lm_mid", "m2c_lm_far"]          # near -> far (camera distance)
TRAJECTORY_CHECK = {"min_cos": 0.9, "mag_ratio": [0.6, 1.6], "cp_err_frac": 0.3, "cp_err_min_px": 16,
                    "reversal_tol": 0.1, "jump_factor": 3.0, "jump_px": 12, "progress_tol": 0.25}
LANDMARK_GATE = {"min_height_cells": 0.5, "min_width_cells": 0.25, "min_area_cells": 0.1, "min_control_contrast": -1.0,
                 "require_visible_all_frames": True, "min_displacement_px": 24, "min_visible_area_frac": 0.7}
MIN_CLEARANCE_M = 1.0


def ease(s: float, mix: float) -> float:
    return mix * s + (1.0 - mix) * (0.5 - 0.5 * math.cos(math.pi * s))


def yaw_about_world_z(c2w: np.ndarray, angle_rad: float) -> np.ndarray:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    out = c2w.copy()
    out[:3, :3] = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]) @ c2w[:3, :3]
    return out


def camera_samples(move: dict = CAMERA_MOVE, frames: int = FRAMES, fps: int = FPS) -> CameraTrajectory:
    """One camera_to_world sample per output frame (t = k / fps)."""
    target = np.asarray(move["target"], dtype=np.float64)
    (a0, a1), (r0, r1), (h0, h1) = move["azimuth_deg"], move["radius_m"], move["height_m"]
    c2w = []
    for k in range(frames):
        e = ease(k / (frames - 1), move["ease_linear_mix"])
        az, r, h = math.radians(a0 + (a1 - a0) * e), r0 + (r1 - r0) * e, h0 + (h1 - h0) * e
        eye = np.array([target[0] + r * math.sin(az), target[1] - r * math.cos(az), h])
        c2w.append(yaw_about_world_z(conventions.look_at(eye, target), math.radians(move["yaw_offset_deg"])))
    t = [k / fps for k in range(frames)]
    return CameraTrajectory.from_c2w(t, np.stack(c2w), lens_mm=np.full(frames, move["lens_mm"]),
                                     interpolation="catmull_rom",
                                     meta={"provenance": {"source": "authored"}, "move": "orbit+push-in, look-at"})


def add_banner(m, oc_id, pass_index, color, center, size, facing="-Y"):
    w, h = size
    dims = (w, 0.02, h) if facing in ("-Y", "+Y") else (0.02, w, h)
    o = temple.box(dims, center, m[f"banner_{color}"])
    o.name = oc_id
    temple.tag(o, oc_id, pass_index)
    return o


def clearance_per_frame(scene, cam, frames: int) -> dict:
    """Exact minimum distance from the camera centre to every tagged mesh (evaluated), per frame."""
    meshes = [o for o in common.tagged_objects(scene, types={"MESH"})]
    rows = {str(o["oc_id"]): [] for o in meshes}
    heights = []
    for f in range(scene.frame_start, scene.frame_start + frames):
        scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        eye = cam.evaluated_get(dg).matrix_world.translation.copy()
        heights.append(float(eye.z))
        for o in meshes:
            oe = o.evaluated_get(dg)
            inv = oe.matrix_world.inverted()
            ok, loc, _normal, _idx = oe.closest_point_on_mesh(inv @ eye)
            rows[str(o["oc_id"])].append(float((oe.matrix_world @ loc - eye).length) if ok else None)
    scene.frame_set(scene.frame_start)
    per_obj = {k: round(min(v for v in vals if v is not None), 4) for k, vals in rows.items()}
    nearest = min(per_obj, key=per_obj.get)
    return {"min_distance_m_per_object": per_obj, "min_distance_m": per_obj[nearest], "nearest_object": nearest,
            "camera_height_m": [round(min(heights), 4), round(max(heights), 4)],
            "minimum_required_m": MIN_CLEARANCE_M, "ok": per_obj[nearest] >= MIN_CLEARANCE_M}


def proxies() -> list[dict]:
    """Conservative AABB proxies (scene units, metres) for camera.retarget.clearance_report."""
    out = [{"type": "aabb", "id": "floor", "min": [-60, -40, -1.0], "max": [60, 80, 0.0]}]
    for side in (-1, 1):
        for y in temple.PILLAR_YS:
            x = side * temple.PILLAR_X
            out.append({"type": "aabb", "id": f"pillar_{x:+.1f}_{y:+.1f}", "min": [x - 0.55, y - 0.55, 0.0],
                        "max": [x + 0.55, y + 0.55, 4.5]})
    out += [{"type": "aabb", "id": "wall_left", "min": [-7.3, -4.0, 0.0], "max": [-6.7, 16.0, 3.5]},
            {"type": "aabb", "id": "wall_right", "min": [6.7, -4.0, 0.0], "max": [7.3, 16.0, 3.5]},
            {"type": "aabb", "id": "wall_back", "min": [-7.3, 13.2, 0.0], "max": [7.3, 13.8, 5.0]},
            {"type": "aabb", "id": "shrine", "min": [-4.5, 4.6, 0.0], "max": [4.5, 11.0, 9.0]},
            {"type": "aabb", "id": "actor", "min": [ACTOR_AT[0] - 0.9, ACTOR_AT[1] - 0.6, 0.0],
             "max": [ACTOR_AT[0] + 1.35, ACTOR_AT[1] + 0.6, 3.2]}]
    return out


def build(out_path: str, spec_path: str | None, banners: list[tuple] | None = None) -> dict:
    banners = BANNERS if banners is None else banners
    scene = temple.setup_scene()
    m = temple.make_materials()
    m.update({f"banner_{k}": temple.flat_material(f"m2c_banner_{k}", v) for k, v in BANNER_COLORS.items()})
    cam = temple.add_camera(scene)
    temple.build_environment(m)
    temple.add_shiva(m)
    asura = temple.build_asura(m)
    asura.name = "m2c_asura"
    asura.location = ACTOR_AT
    temple.tag(asura, "m2c_asura", 1)
    for oc_id, pidx, color, center, size, facing in banners:
        add_banner(m, oc_id, pidx, color, center, size, facing)
    temple.add_sun(scene)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    traj = camera_samples()
    npz = os.path.join(out_dir, "camera_motion.npz")
    traj.save_npz(npz)
    motion = {"schema_version": 1, "id": "m2c_orbit_push_in_v1", "units": "meters",
              "coordinate_system": "blender_z_up", "pose_convention": "camera_to_world",
              "rotation_format": "quaternion_wxyz", "trajectory": "camera_motion.npz",
              "trajectory_sha256": hashing.file_sha256(npz),
              "intrinsics": {"lens_mm": CAMERA_MOVE["lens_mm"], "sensor_width_mm": CAMERA_MOVE["sensor_mm"],
                             "sensor_height_mm": 24.0, "sensor_fit": CAMERA_MOVE["sensor_fit"],
                             "resolution_x": RES[0], "resolution_y": RES[1], "resolution_percentage": 100,
                             "clip_start": CAMERA_MOVE["clip_start"], "clip_end": CAMERA_MOVE["clip_end"]},
              "duration": f"{FRAMES}/{FPS}" if FRAMES % FPS else str(FRAMES // FPS),
              "target_bindings": ["m2c_asura.chest"],
              "constraints": {"minimum_clearance_m": MIN_CLEARANCE_M, "preserve_roll": True},
              "provenance": {"source": "authored", "confidence": "verified_in_scene", "scale": "metric_verified",
                             "notes": "M2-C orbit + push-in, look-at with a constant yaw framing offset"}}
    motion_path = os.path.join(out_dir, "camera_motion.json")
    common.write_json(motion_path, motion)
    # Session A importer: one LINEAR key per frame on the scene camera, intrinsics from the manifest; saves the .blend
    oc_import_camera.apply(SimpleNamespace(samples=npz, time_key="t", intrinsics=motion_path, camera_name=cam.name,
                                           frame_start=scene.frame_start, set_scene_camera=True, save=out_path))
    clearance = clearance_per_frame(scene, cam, FRAMES)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_path))

    eyes = traj.position
    info = {"camera_start_m": [round(v, 4) for v in eyes[0]], "camera_end_m": [round(v, 4) for v in eyes[-1]],
            "chord_m": round(float(np.linalg.norm(eyes[-1] - eyes[0])), 4),
            "path_m": round(float(np.linalg.norm(np.diff(eyes, axis=0), axis=1).sum()), 4),
            "peak_speed_m_s": round(float(np.linalg.norm(np.diff(eyes, axis=0), axis=1).max() * FPS), 4),
            "orbit_deg": CAMERA_MOVE["azimuth_deg"][1] - CAMERA_MOVE["azimuth_deg"][0],
            "radius_m": CAMERA_MOVE["radius_m"]}
    if spec_path:
        common.write_json(spec_path, {
            "shot": "m2c_camera",
            "purpose": ("M2-C: M2-A's representative temple and rigid humanoid proxy (static); ONE authored moving camera "
                        "(orbit + push-in, fixed lens); static camera -> moving camera is the only new axis"),
            "frames": FRAMES, "fps": FPS, "resolution": list(RES), "camera": temple.CAMERA,
            "scene": dict(temple.scene_spec(), actor_at=ACTOR_AT, banner_colors=BANNER_COLORS,
                          banners=[{"oc_id": b[0], "pass_index": b[1], "color": b[2], "center": b[3], "size": b[4],
                                    "facing": b[5]} for b in banners]),
            "choreography": {"m2c_asura": {"motion": "static (no keys)", "at": ACTOR_AT},
                             "camera_move": dict(CAMERA_MOVE, **info),
                             "camera_motion": {"manifest": "camera_motion.json", "samples": "camera_motion.npz"}},
            "camera_clearance": clearance,
            "clearance_proxies": proxies(),
            "tracking": {
                "subjects": dict({
                    "m2c_asura": {"color": "red", "role": "primary",
                                  "checks": {"position": {"tol_px": 32, "area_tol": 0.25},
                                             "approach": {"min_gain_frac": 0.5, "monotone_tol": 0.15}}}},
                    **{b[0]: {"color": b[2], "role": "primary", "layer": b[0].rsplit("_", 1)[-1], "gate": LANDMARK_GATE,
                              "checks": {"trajectory": TRAJECTORY_CHECK}} for b in banners},
                    m2a_shiva={"color": "blue", "role": "secondary", "checks": {"report_only": {}}}),
                "ground": ["m2a_floor"],
                "static_structures": [],
                "gate": {"min_height_cells": 2.0, "min_area_cells": 2.0, "min_width_cells": 1.5,
                         "min_control_contrast": 0.08, "require_in_frame": True},
                "parallax": {"layers": [b[0] for b in banners if b[0] in LANDMARK_LAYERS], "min_gt_separation": 1.25,
                             "ratio_tol": 1.35},
                "camera_contract": {"samples": "camera_motion.npz", "max_position_err_m": 0.001,
                                    "max_angle_err_deg": 0.05},
                "clearance": {"min_m": MIN_CLEARANCE_M},
                "occlusion_reveal": {"subjects": {"m2c_lm_far": 0.9, "m2a_shiva": 0.5}},
                "notes": ("static-structure drift is not meaningful under a moving camera (omitted). Landmark banners are "
                          "thin cloth on architecture: the depth control carries the pillar shafts they hang on, so "
                          "their own control contrast is not gated. Landmarks may be partly occluded (visible area >= 70% "
                          "of their maximum): the far banner is partly behind the third pillar early in the move and "
                          "revealed by it, which is the occlusion/reveal evidence (report-only). Generated viewpoint evidence is image-space only "
                          "(landmark trajectories, parallax, framing, occlusion); no camera pose is inferred."),
            },
            "classification": {
                "pass": ("every landmark trajectory followed (direction cos >= 0.9 vs GT, magnitude 0.6-1.6x, checkpoint "
                         "error <= max(16 px, 0.3 x GT displacement), monotone progress, no jump, progress within 0.25 of "
                         "GT at the checkpoints) AND parallax order of the landmark displacements = GT with pairwise "
                         "ratios within x/1.35 AND subject framing followed (position + approach) AND visual inspection "
                         "agrees it reads as an authored viewpoint change with coherent architecture, not scene morphing"),
                "partial": ("camera direction correct for the landmarks but parallax magnitude/order weakened, or framing "
                            "follows but architecture deforms materially, or the motion stalls/jitters, or some depth "
                            "layers follow while others morph, or not controlled enough for production use"),
                "fail": ("scene effectively static, camera direction contradicted, apparent motion mainly from morphing, "
                         "relative parallax substantially wrong, too incoherent to evaluate, or major unexplained "
                         "reversals/cuts"),
                "owner_playback": "not required for classification; recorded separately if given",
                "retry": "at most one evidence-driven retry, only after PARTIAL or FAIL; none after a PASS",
            },
            "blender": common.blender_version(),
        })
    print(f"[oc] M2-C temple camera scene saved: {out_path} ({info})")
    return {"clearance": clearance, "move": info}


def main() -> None:
    p = argparse.ArgumentParser(prog="build_temple_camera_scene")
    p.add_argument("--out", required=True)
    p.add_argument("--spec", default=None)
    a = p.parse_args(common.script_args())
    build(a.out, a.spec)


if __name__ == "__main__":
    main()
