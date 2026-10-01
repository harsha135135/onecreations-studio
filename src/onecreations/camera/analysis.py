"""Trajectory statistics and preview metadata for the camera/motion library (v1 §10)."""

from __future__ import annotations

import numpy as np

from onecreations.camera.trajectory import CameraTrajectory
from onecreations.geometry import conventions, quat


def _round(x, nd: int = 6):
    if isinstance(x, np.ndarray):
        return [_round(v, nd) for v in x.tolist()]
    if isinstance(x, (list, tuple)):
        return [_round(v, nd) for v in x]
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), nd)


def trajectory_stats(traj: CameraTrajectory, rate: float = 240.0, world_up=(0.0, 0.0, 1.0)) -> dict:
    """Kinematic summary on a uniform resampling at `rate` Hz.

    Derivatives are finite differences (second order, including the ends) of a C1 spline, so peak
    acceleration/jerk are approximations; jerk is especially sensitive to the spline's knots.
    """
    n = max(3, int(round(traj.duration * rate)) + 1)
    ts = np.linspace(traj.start, traj.end, n)
    pos, qs = traj.evaluate(ts)
    c2w = conventions.compose(pos, qs)

    seg = np.linalg.norm(np.diff(pos, axis=0), axis=1)
    vel = np.gradient(pos, ts, axis=0, edge_order=2)
    speed = np.linalg.norm(vel, axis=1)
    acc = np.gradient(vel, ts, axis=0, edge_order=2)
    jerk = np.gradient(acc, ts, axis=0, edge_order=2)
    dt = np.diff(ts)
    ang = np.array([quat.angle_between(qs[i], qs[i + 1]) for i in range(n - 1)]) / dt
    ang_mid = 0.5 * (ts[:-1] + ts[1:])
    ang_acc = np.gradient(ang, ang_mid) if len(ang) > 1 else np.zeros(1)
    roll = np.degrees(conventions.roll_angle(c2w, world_up))
    fwd = conventions.camera_forward(c2w)

    finite_roll = roll[np.isfinite(roll)]
    return {
        "duration_s": _round(traj.duration),
        "samples": int(len(traj)),
        "analysis_rate_hz": float(rate),
        "path_length_m": _round(seg.sum()),
        "net_displacement_m": _round(np.linalg.norm(pos[-1] - pos[0])),
        "speed_mps": {"max": _round(speed.max()), "mean": _round(speed.mean())},
        "accel_mps2_max": _round(np.linalg.norm(acc, axis=1).max()),
        "jerk_mps3_max": _round(np.linalg.norm(jerk, axis=1).max()),
        "angular_speed_dps_max": _round(np.degrees(ang.max())),
        "angular_accel_dps2_max": _round(np.degrees(np.abs(ang_acc).max())),
        "roll_deg": {"min": _round(finite_roll.min()) if finite_roll.size else None,
                     "max": _round(finite_roll.max()) if finite_roll.size else None,
                     "undefined_samples": int((~np.isfinite(roll)).sum())},
        "bbox_m": {"min": _round(pos.min(axis=0)), "max": _round(pos.max(axis=0))},
        "start": {"position": _round(pos[0]), "forward": _round(fwd[0])},
        "end": {"position": _round(pos[-1]), "forward": _round(fwd[-1])},
    }


def preview_metadata(traj: CameraTrajectory, motion_id: str | None = None) -> dict:
    """Stats plus provenance, as stored next to a motion-library entry."""
    return {
        "id": motion_id,
        "stats": trajectory_stats(traj),
        "provenance": traj.meta.get("provenance", {}),
        "operations": traj.meta.get("operations", []),
        "has_lens_curve": traj.lens_mm is not None,
    }
