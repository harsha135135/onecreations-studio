"""Shared helpers for OneCreations Blender scripts (run inside Blender: bpy + stdlib + numpy only).

Puts the repo's `src/` on sys.path so scripts reuse the exact same time, hashing and geometry code as the main
package (no pydantic inside Blender — validation happens outside, on the files these scripts write).
"""

from __future__ import annotations

import json
import os
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from onecreations import hashing  # noqa: E402
from onecreations.geometry.intrinsics import BlenderCameraParams  # noqa: E402

EXPORTER_VERSION = "0.1.0"


def script_args() -> list[str]:
    argv = sys.argv
    return argv[argv.index("--") + 1:] if "--" in argv else []


def blender_version() -> str:
    return bpy.app.version_string


def scene_fps(scene) -> Fraction:
    """Exact scene frame rate: fps / fps_base, with fps_base read at 1e-6 precision (1.001 → 24000/1001)."""
    base = Fraction(f"{scene.render.fps_base:.6f}").limit_denominator(100000)
    return Fraction(scene.render.fps) / base


def camera_params(cam_obj, scene) -> BlenderCameraParams:
    cam = cam_obj.data
    if cam.type != "PERSP":
        raise ValueError(f"camera {cam_obj.name!r} is {cam.type}; only PERSP cameras are supported")
    r = scene.render
    return BlenderCameraParams(
        lens_mm=float(cam.lens), sensor_width_mm=float(cam.sensor_width), sensor_height_mm=float(cam.sensor_height),
        sensor_fit=cam.sensor_fit, shift_x=float(cam.shift_x), shift_y=float(cam.shift_y),
        resolution_x=int(r.resolution_x), resolution_y=int(r.resolution_y),
        resolution_percentage=int(r.resolution_percentage),
        pixel_aspect_x=float(r.pixel_aspect_x), pixel_aspect_y=float(r.pixel_aspect_y),
        clip_start=float(cam.clip_start), clip_end=float(cam.clip_end))


def to_numpy(matrix) -> np.ndarray:
    return np.array([list(row) for row in matrix], dtype=np.float64)


def rigid_matrix(matrix_world) -> np.ndarray:
    """camera_to_world without scale. Refuses mirrored (negative-determinant) transforms."""
    m3 = matrix_world.to_3x3()
    if m3.determinant() <= 0:
        raise ValueError("object transform is mirrored or degenerate (det <= 0); fix the rig before export")
    loc, rot, _scale = matrix_world.decompose()
    out = np.eye(4)
    out[:3, :3] = to_numpy(rot.to_matrix())
    out[:3, 3] = list(loc)
    return out


def write_json(path: str, obj) -> None:
    hashing.write_canonical_json(path, obj)


def read_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_arrays(path: str, arrays: dict) -> dict:
    """Write an NPZ and return its ArrayFile record (content digest, not file-byte hash)."""
    np.savez_compressed(path, **arrays)
    return {"file": os.path.basename(path), "digest": hashing.array_digest(arrays), "keys": sorted(arrays)}


def tagged_objects(scene, types=None) -> list:
    """Objects carrying an `oc_id` custom property, sorted by oc_id for deterministic output."""
    objs = [o for o in scene.objects if "oc_id" in o.keys() and (types is None or o.type in types)]
    return sorted(objs, key=lambda o: str(o["oc_id"]))


def load_intrinsics_dict(path: str) -> dict:
    """Accept intrinsics JSON, an export manifest (camera.intrinsics) or a CameraMotion manifest (intrinsics, inline
    or as a relative path)."""
    data = read_json(path)
    if isinstance(data.get("camera"), dict) and "intrinsics" in data["camera"]:
        return data["camera"]["intrinsics"]
    if "intrinsics" in data:
        intr = data["intrinsics"]
        if isinstance(intr, str):
            return read_json(os.path.join(os.path.dirname(os.path.abspath(path)), intr))
        return intr
    return data
