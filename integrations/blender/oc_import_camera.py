"""Apply a trajectory (NPZ from oc_export or CameraTrajectory.save_npz, or CSV) to a Blender camera.

    blender -b scene.blend --factory-startup --python oc_import_camera.py -- --samples camera_samples.npz
        [--time-key t] [--intrinsics intrinsics_or_manifest.json] [--camera-name OC_Camera_Import]
        [--frame-start N] [--set-scene-camera] --save out.blend

Each sample becomes a keyframe at frame_start + t × scene_fps (fractional frames allowed), with location and
rotation_quaternion keyed and LINEAR interpolation. Between keys Blender interpolates quaternions per component
(not slerp), so import densely sampled trajectories (≥ one sample per frame) when the in-between matters.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import oc_blender_common as common  # noqa: E402
from onecreations.geometry import quat  # noqa: E402

INTRINSIC_ATTRS = {"lens_mm": "lens", "sensor_width_mm": "sensor_width", "sensor_height_mm": "sensor_height",
                   "sensor_fit": "sensor_fit", "shift_x": "shift_x", "shift_y": "shift_y",
                   "clip_start": "clip_start", "clip_end": "clip_end"}


def load_samples(path: str, time_key: str) -> dict:
    if path.lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        out = {"t": np.array([float(r["t"]) for r in rows]),
               "position": np.array([[float(r[c]) for c in ("x", "y", "z")] for r in rows]),
               "quaternion_wxyz": np.array([[float(r[c]) for c in ("qw", "qx", "qy", "qz")] for r in rows])}
        if rows and "lens_mm" in rows[0]:
            out["lens_mm"] = np.array([float(r["lens_mm"]) for r in rows])
        return out
    with np.load(path, allow_pickle=False) as z:
        out = {"t": z[time_key], "position": z["position"], "quaternion_wxyz": z["quaternion_wxyz"]}
        if "lens_mm" in z.files:
            out["lens_mm"] = z["lens_mm"]
        return out


def apply(args) -> None:
    scene = bpy.context.scene
    s = load_samples(args.samples, args.time_key)
    if np.any(np.diff(s["t"]) <= 0):
        raise ValueError(f"time key {args.time_key!r} is not strictly increasing (holds in t_source?); use output time 't'")
    fps = common.scene_fps(scene)
    frame_start = scene.frame_start if args.frame_start is None else args.frame_start

    cam = bpy.data.objects.get(args.camera_name)
    if cam is None:
        cam = bpy.data.objects.new(args.camera_name, bpy.data.cameras.new(args.camera_name))
        scene.collection.objects.link(cam)
    elif cam.type != "CAMERA":
        raise ValueError(f"{args.camera_name!r} exists and is not a camera")
    cam.animation_data_clear()
    if cam.data.animation_data:
        cam.data.animation_data_clear()
    cam.parent = None
    cam.scale = (1.0, 1.0, 1.0)
    cam.rotation_mode = "QUATERNION"

    if args.intrinsics:
        intr = common.load_intrinsics_dict(args.intrinsics)
        for key, attr in INTRINSIC_ATTRS.items():
            if key in intr:
                setattr(cam.data, attr, intr[key])

    qs = quat.make_continuous(np.asarray(s["quaternion_wxyz"], dtype=np.float64))
    lens = s.get("lens_mm")
    animate_lens = lens is not None and np.ptp(lens) > 1e-9
    for i, t in enumerate(s["t"]):
        frame = float(frame_start + float(t) * float(fps))
        cam.location = [float(v) for v in s["position"][i]]
        cam.rotation_quaternion = [float(v) for v in qs[i]]
        cam.keyframe_insert("location", frame=frame)
        cam.keyframe_insert("rotation_quaternion", frame=frame)
        if animate_lens:
            cam.data.lens = float(lens[i])
            cam.data.keyframe_insert("lens", frame=frame)
    if lens is not None and not animate_lens:
        cam.data.lens = float(lens[0])
    for datablock in (cam, cam.data):
        ad = datablock.animation_data
        if ad and ad.action:
            for fc in ad.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
    if args.set_scene_camera:
        scene.camera = cam
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save))
    print(f"[oc] imported {len(s['t'])} samples onto {cam.name!r} → {args.save}")


def main() -> None:
    p = argparse.ArgumentParser(prog="oc_import_camera")
    p.add_argument("--samples", required=True)
    p.add_argument("--time-key", default="t")
    p.add_argument("--intrinsics")
    p.add_argument("--camera-name", default="OC_Camera_Import")
    p.add_argument("--frame-start", type=int)
    p.add_argument("--set-scene-camera", action="store_true")
    p.add_argument("--save", required=True)
    apply(p.parse_args(common.script_args()))


if __name__ == "__main__":
    main()
