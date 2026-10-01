"""Minimal COLMAP text-model import (Session A): `images.txt` poses and PINHOLE/SIMPLE_PINHOLE `cameras.txt`.

COLMAP stores world→camera (R, t) in OpenCV camera axes. We convert to Blender camera_to_world. COLMAP worlds have an
arbitrary up axis and unknown scale, so imported trajectories are tagged `scale: unknown`, `up_axis: unaligned`;
use `normalize.align_up` / `set_metric_scale` with real evidence before treating them as metric.

Deferred: distortion models, rolling shutter, gyro alignment, gap repair (v1 §10 FPV pipeline).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from onecreations.camera.trajectory import CameraTrajectory
from onecreations.geometry import conventions, quat
from onecreations.timebase import FrameRate


def parse_images_txt(path: str | Path) -> list[dict]:
    lines = [ln.rstrip("\n") for ln in Path(path).read_text(encoding="utf-8").splitlines(keepends=True)
             if not ln.startswith("#")]
    images, i = [], 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        parts = lines[i].split()
        if len(parts) < 10:
            raise ValueError(f"{path}: malformed image line {lines[i]!r}")
        images.append({
            "image_id": int(parts[0]),
            "qvec_wxyz": [float(v) for v in parts[1:5]],
            "tvec": [float(v) for v in parts[5:8]],
            "camera_id": int(parts[8]),
            "name": " ".join(parts[9:]),
        })
        i += 2  # the following POINTS2D line (possibly empty) belongs to this image
    return images


def parse_cameras_txt(path: str | Path) -> dict[int, dict]:
    cams = {}
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        p = ln.split()
        cam_id, model, w, h = int(p[0]), p[1], int(p[2]), int(p[3])
        params = [float(v) for v in p[4:]]
        if model == "SIMPLE_PINHOLE":
            f, cx, cy = params
            fx = fy = f
        elif model == "PINHOLE":
            fx, fy, cx, cy = params
        else:
            raise NotImplementedError(f"COLMAP camera model {model} not supported yet (Session A: pinhole only)")
        cams[cam_id] = {"model": model, "width": w, "height": h,
                        "K": [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]]}
    return cams


def colmap_c2w_blender(qvec_wxyz, tvec) -> np.ndarray:
    r_wc = quat.to_matrix(np.asarray(qvec_wxyz, dtype=np.float64))
    t = np.asarray(tvec, dtype=np.float64)
    c2w_cv = np.eye(4)
    c2w_cv[:3, :3] = r_wc.T
    c2w_cv[:3, 3] = -r_wc.T @ t
    return conventions.opencv_c2w_to_blender(c2w_cv)


def images_to_trajectory(images: list[dict], fps: FrameRate | float, order: str = "name") -> CameraTrajectory:
    """Frames ordered by image name (default) or image_id, timed at index / fps."""
    if order not in ("name", "image_id"):
        raise ValueError("order must be 'name' or 'image_id'")
    imgs = sorted(images, key=lambda im: im[order])
    rate = float(fps.fps) if isinstance(fps, FrameRate) else float(fps)
    c2w = np.stack([colmap_c2w_blender(im["qvec_wxyz"], im["tvec"]) for im in imgs])
    t = np.arange(len(imgs)) / rate
    meta = {"provenance": {"source": "colmap", "confidence": "estimated", "scale": "unknown",
                           "up_axis": "unaligned"},
            "frames": [im["name"] for im in imgs]}
    return CameraTrajectory.from_c2w(t, c2w, meta=meta)


def write_images_txt(path: str | Path, c2w_blender: np.ndarray, names: list[str], camera_id: int = 1) -> None:
    """Write Blender c2w poses as a COLMAP images.txt (used for tests and round trips)."""
    lines = ["# Image list with two lines of data per image:", "#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME",
             "#   POINTS2D[] as (X, Y, POINT3D_ID)"]
    for i, (m, name) in enumerate(zip(c2w_blender, names), start=1):
        c2w_cv = conventions.blender_c2w_to_opencv(m)
        r_wc = c2w_cv[:3, :3].T
        t = -r_wc @ c2w_cv[:3, 3]
        q = quat.from_matrix(r_wc)
        lines.append(" ".join([str(i), *(repr(float(v)) for v in q), *(repr(float(v)) for v in t), str(camera_id), name]))
        lines.append("")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
