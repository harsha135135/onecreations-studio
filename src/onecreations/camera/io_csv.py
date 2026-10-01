"""Plain-text trajectory exchange: `t,x,y,z,qw,qx,qy,qz[,lens_mm]` (seconds, meters, Blender camera convention)."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from onecreations.camera.trajectory import CameraTrajectory

HEADER = ["t", "x", "y", "z", "qw", "qx", "qy", "qz"]


def write_csv(traj: CameraTrajectory, path: str | Path) -> None:
    cols = HEADER + (["lens_mm"] if traj.lens_mm is not None else [])
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for i in range(len(traj)):
            row = [traj.t[i], *traj.position[i], *traj.quaternion[i]]
            if traj.lens_mm is not None:
                row.append(traj.lens_mm[i])
            w.writerow([repr(float(v)) for v in row])


def read_csv(path: str | Path, **kwargs) -> CameraTrajectory:
    with Path(path).open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"{path}: no samples")
    missing = [c for c in HEADER if c not in rows[0]]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    a = np.array([[float(r[c]) for c in HEADER] for r in rows])
    lens = np.array([float(r["lens_mm"]) for r in rows]) if "lens_mm" in rows[0] else None
    return CameraTrajectory(a[:, 0], a[:, 1:4], a[:, 4:8], lens, **kwargs)
