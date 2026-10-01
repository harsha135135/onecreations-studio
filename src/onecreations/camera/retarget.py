"""Retarget a library trajectory into a new scene and check clearance against collision proxies.

Retargeting is a gravity-preserving similarity (translation + yaw + uniform scale) from a source anchor to a target
anchor, plus optional time scaling. Collision-aware *path adjustment* is deferred: this module reports violations so an
artist (or a later solver) can fix them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from onecreations.camera.normalize import _with_op, apply_similarity, yaw_rotation
from onecreations.camera.trajectory import CameraTrajectory


@dataclass(frozen=True)
class Anchor:
    """A subject/scene anchor: position (m) and yaw (degrees about +Z)."""
    position: tuple[float, float, float]
    yaw_deg: float = 0.0

    def rotation(self) -> np.ndarray:
        return yaw_rotation(self.yaw_deg)


def retarget(traj: CameraTrajectory, source: Anchor, target: Anchor, scale: float = 1.0,
             time_scale: float = 1.0) -> CameraTrajectory:
    """Move the motion so it relates to `target` as it related to `source`; optionally scale space and time."""
    if time_scale <= 0:
        raise ValueError("time_scale must be positive")
    r = target.rotation() @ source.rotation().T
    t = np.asarray(target.position, dtype=np.float64) - scale * r @ np.asarray(source.position, dtype=np.float64)
    out = apply_similarity(traj, rotation=r, translation=t, scale=scale,
                           op={"op": "retarget", "source": [list(source.position), source.yaw_deg],
                               "target": [list(target.position), target.yaw_deg], "scale": scale,
                               "time_scale": time_scale},
                           provenance={"source": "retargeted"})
    if time_scale != 1.0:
        out = _with_op(out, {"op": "time_scale", "factor": time_scale})
        out.t = traj.t[0] + (traj.t - traj.t[0]) * time_scale
    return out


@dataclass(frozen=True)
class Sphere:
    id: str
    center: tuple[float, float, float]
    radius: float

    def distance(self, pts: np.ndarray) -> np.ndarray:
        return np.linalg.norm(pts - np.asarray(self.center), axis=1) - self.radius


@dataclass(frozen=True)
class AABB:
    id: str
    min: tuple[float, float, float]
    max: tuple[float, float, float]

    def distance(self, pts: np.ndarray) -> np.ndarray:
        lo, hi = np.asarray(self.min), np.asarray(self.max)
        center, half = (lo + hi) / 2, (hi - lo) / 2
        q = np.abs(pts - center) - half
        outside = np.linalg.norm(np.maximum(q, 0.0), axis=1)
        inside = np.minimum(np.max(q, axis=1), 0.0)
        return outside + inside  # signed: negative inside


def proxies_from_dicts(items: list[dict]) -> list[Sphere | AABB]:
    out: list[Sphere | AABB] = []
    for it in items:
        if it["type"] == "sphere":
            out.append(Sphere(it["id"], tuple(it["center"]), float(it["radius"])))
        elif it["type"] == "aabb":
            out.append(AABB(it["id"], tuple(it["min"]), tuple(it["max"])))
        else:
            raise ValueError(f"unknown proxy type {it['type']!r}")
    return out


def clearance_report(traj: CameraTrajectory, proxies: list[Sphere | AABB], minimum_clearance_m: float,
                     rate: float = 240.0) -> dict:
    """Sample the path densely and report every interval where clearance < minimum_clearance_m."""
    n = max(2, int(round(traj.duration * rate)) + 1)
    ts = np.linspace(traj.start, traj.end, n)
    pos, _ = traj.evaluate(ts)
    violations = []
    overall = np.inf
    for proxy in proxies:
        d = proxy.distance(pos)
        overall = min(overall, float(d.min()))
        bad = d < minimum_clearance_m
        if not bad.any():
            continue
        edges = np.flatnonzero(np.diff(np.concatenate([[0], bad.astype(int), [0]])))
        for start, stop in zip(edges[::2], edges[1::2]):
            seg = slice(start, stop)
            violations.append({"proxy": proxy.id, "start_s": round(float(ts[start]), 6),
                               "end_s": round(float(ts[stop - 1]), 6),
                               "min_distance_m": round(float(d[seg].min()), 6)})
    return {"minimum_clearance_m": minimum_clearance_m,
            "min_distance_m": None if not proxies else round(overall, 6),
            "ok": not violations, "violations": violations}
