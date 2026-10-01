"""Normalization of recovered or authored trajectories: re-origin, gravity/up alignment, metric scale.

Every operation returns a new trajectory and appends an entry to meta["operations"], so a library entry records how
its coordinates were produced (v1 §10: tag scale provenance, never present a guessed scale as recovered).
"""

from __future__ import annotations

import copy

import numpy as np

from onecreations.camera.trajectory import CameraTrajectory
from onecreations.geometry import quat


def _with_op(traj: CameraTrajectory, op: dict, provenance: dict | None = None) -> CameraTrajectory:
    meta = copy.deepcopy(traj.meta)
    meta.setdefault("operations", []).append(op)
    meta.setdefault("provenance", {}).update(provenance or {})
    return CameraTrajectory(traj.t.copy(), traj.position.copy(), traj.quaternion.copy(),
                            None if traj.lens_mm is None else traj.lens_mm.copy(), traj.interpolation, meta)


def rotation_between(a, b) -> np.ndarray:
    """Minimal 3×3 rotation taking direction a onto direction b."""
    a = np.asarray(a, dtype=np.float64) / np.linalg.norm(a)
    b = np.asarray(b, dtype=np.float64) / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if c < -1 + 1e-12:  # opposite: rotate π about any axis orthogonal to a
        axis = np.cross(a, [1.0, 0.0, 0.0])
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(a, [0.0, 1.0, 0.0])
        return quat.to_matrix(quat.from_axis_angle(axis, np.pi))
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))


def yaw_rotation(deg: float) -> np.ndarray:
    return quat.to_matrix(quat.from_axis_angle([0.0, 0.0, 1.0], np.radians(deg)))


def apply_similarity(traj: CameraTrajectory, rotation=None, translation=None, scale: float = 1.0,
                     op: dict | None = None, provenance: dict | None = None) -> CameraTrajectory:
    """World-space similarity: p' = s·R·p + t; camera orientation R_cam' = R·R_cam. Scale must be positive."""
    if scale <= 0:
        raise ValueError("scale must be positive (a negative scale would mirror the camera)")
    r = np.eye(3) if rotation is None else np.asarray(rotation, dtype=np.float64)
    if not np.allclose(r @ r.T, np.eye(3), atol=1e-9) or np.linalg.det(r) < 0:
        raise ValueError("rotation must be a proper rotation matrix")
    t = np.zeros(3) if translation is None else np.asarray(translation, dtype=np.float64)
    q_r = quat.from_matrix(r)
    out = _with_op(traj, op or {"op": "similarity", "rotation": r.tolist(), "translation": t.tolist(), "scale": scale},
                   provenance)
    out.position = scale * traj.position @ r.T + t
    out.quaternion = quat.make_continuous(quat.multiply(np.broadcast_to(q_r, traj.quaternion.shape), traj.quaternion))
    return out


def reorigin(traj: CameraTrajectory, origin) -> CameraTrajectory:
    origin = np.asarray(origin, dtype=np.float64)
    return apply_similarity(traj, translation=-origin, op={"op": "reorigin", "origin": origin.tolist()})


def align_up(traj: CameraTrajectory, measured_up) -> CameraTrajectory:
    """Rotate the world so `measured_up` (e.g. a gravity estimate in the solve's frame) maps to +Z."""
    r = rotation_between(measured_up, [0.0, 0.0, 1.0])
    return apply_similarity(traj, rotation=r, op={"op": "align_up", "measured_up": list(map(float, measured_up))},
                            provenance={"up_axis": "aligned"})


def scale_from_known_distance(measured: float, true_m: float) -> float:
    if measured <= 0 or true_m <= 0:
        raise ValueError("distances must be positive")
    return true_m / measured


def set_metric_scale(traj: CameraTrajectory, factor: float, evidence: str) -> CameraTrajectory:
    """Scale positions about the world origin; `evidence` says how the factor was established."""
    return apply_similarity(traj, scale=factor, op={"op": "metric_scale", "factor": factor, "evidence": evidence},
                            provenance={"scale": "metric_estimated"})
