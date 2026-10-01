"""Sampled camera trajectories: canonical position + orientation over time (v1 §10).

Samples are Blender-convention camera_to_world poses (−Z forward, +Y up, Z-up world, meters) at strictly increasing
times in seconds. Position interpolation is a cubic Hermite spline with Catmull-Rom tangents (passes through every
sample) or linear; rotation is slerp between neighbouring samples; lens (if present) is linear.

NPZ layout (`save_npz` / `load_npz`): t (N,) float64 s · position (N,3) · quaternion_wxyz (N,4) · optional lens_mm (N,)
· meta_json () str.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from onecreations.geometry import conventions, quat

INTERPOLATIONS = ("catmull_rom", "linear")
TIME_TOL = 1e-9


def _as_seconds(times: Iterable) -> np.ndarray:
    out = []
    for t in times:
        out.append(float(t) if isinstance(t, (Fraction, int, float, np.floating, np.integer)) else float(Fraction(t)))
    return np.asarray(out, dtype=np.float64)


def _quadratic_end_derivative(t0, t1, t2, p0, p1, p2) -> np.ndarray:
    """d/dt at t0 of the quadratic through (t0,p0), (t1,p1), (t2,p2) (Lagrange form; works for either end)."""
    return (p0 * (2 * t0 - t1 - t2) / ((t0 - t1) * (t0 - t2))
            + p1 * (t0 - t2) / ((t1 - t0) * (t1 - t2))
            + p2 * (t0 - t1) / ((t2 - t0) * (t2 - t1)))


@dataclass
class CameraTrajectory:
    t: np.ndarray
    position: np.ndarray
    quaternion: np.ndarray
    lens_mm: np.ndarray | None = None
    interpolation: str = "catmull_rom"
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.t = np.asarray(self.t, dtype=np.float64).reshape(-1)
        self.position = np.asarray(self.position, dtype=np.float64).reshape(-1, 3)
        self.quaternion = quat.make_continuous(quat.normalize(np.asarray(self.quaternion, dtype=np.float64).reshape(-1, 4)))
        n = len(self.t)
        if n < 2:
            raise ValueError("a trajectory needs at least two samples (use two identical poses for a locked-off shot)")
        if self.position.shape[0] != n or self.quaternion.shape[0] != n:
            raise ValueError("t, position and quaternion must have the same length")
        if not (np.all(np.isfinite(self.t)) and np.all(np.isfinite(self.position))):
            raise ValueError("non-finite samples")
        if np.any(np.diff(self.t) <= 0):
            raise ValueError("sample times must strictly increase")
        if self.lens_mm is not None:
            self.lens_mm = np.asarray(self.lens_mm, dtype=np.float64).reshape(-1)
            if self.lens_mm.shape[0] != n or np.any(self.lens_mm <= 0):
                raise ValueError("lens_mm must be positive and match the sample count")
        if self.interpolation not in INTERPOLATIONS:
            raise ValueError(f"interpolation must be one of {INTERPOLATIONS}")

    # ------------------------------------------------------------------ construction / export
    @classmethod
    def from_c2w(cls, t: Sequence, c2w: np.ndarray, **kwargs) -> "CameraTrajectory":
        c2w = conventions.validate_rigid(c2w)
        qs = np.stack([quat.from_matrix(m[:3, :3]) for m in c2w])
        return cls(_as_seconds(t), c2w[:, :3, 3], qs, **kwargs)

    def c2w(self) -> np.ndarray:
        return conventions.compose(self.position, self.quaternion)

    @property
    def start(self) -> float:
        return float(self.t[0])

    @property
    def end(self) -> float:
        return float(self.t[-1])

    @property
    def duration(self) -> float:
        return self.end - self.start

    def __len__(self) -> int:
        return len(self.t)

    # ------------------------------------------------------------------ evaluation
    def _locate(self, ts: np.ndarray, clamp: bool) -> tuple[np.ndarray, np.ndarray]:
        if not clamp:
            bad = (ts < self.start - TIME_TOL) | (ts > self.end + TIME_TOL)
            if np.any(bad):
                raise ValueError(f"time {float(ts[bad][0])!r} outside trajectory [{self.start}, {self.end}]")
        ts = np.clip(ts, self.start, self.end)
        idx = np.clip(np.searchsorted(self.t, ts, side="right") - 1, 0, len(self.t) - 2)
        h = self.t[idx + 1] - self.t[idx]
        s = (ts - self.t[idx]) / h
        return idx, s

    def _tangents(self) -> np.ndarray:
        """Catmull-Rom (central-difference) tangents; ends use the derivative of the quadratic through the first/last
        three samples, which keeps end-segment curvature close to the interior."""
        p, t = self.position, self.t
        m = np.empty_like(p)
        if len(t) == 2:
            m[:] = (p[1] - p[0]) / (t[1] - t[0])
            return m
        m[1:-1] = (p[2:] - p[:-2]) / (t[2:] - t[:-2])[:, None]
        m[0] = _quadratic_end_derivative(t[0], t[1], t[2], p[0], p[1], p[2])
        m[-1] = _quadratic_end_derivative(t[-1], t[-2], t[-3], p[-1], p[-2], p[-3])
        return m

    def evaluate(self, times, clamp: bool = False) -> tuple[np.ndarray, np.ndarray]:
        """→ (positions (M,3), quaternions (M,4)) at the given times (seconds or Fractions)."""
        ts = _as_seconds(np.atleast_1d(times))
        idx, s = self._locate(ts, clamp)
        p0, p1 = self.position[idx], self.position[idx + 1]
        if self.interpolation == "linear":
            pos = p0 + (p1 - p0) * s[:, None]
        else:
            m = self._tangents()
            h = (self.t[idx + 1] - self.t[idx])[:, None]
            s2, s3 = s * s, s * s * s
            h00 = (2 * s3 - 3 * s2 + 1)[:, None]
            h10 = (s3 - 2 * s2 + s)[:, None]
            h01 = (-2 * s3 + 3 * s2)[:, None]
            h11 = (s3 - s2)[:, None]
            pos = h00 * p0 + h10 * h * m[idx] + h01 * p1 + h11 * h * m[idx + 1]
        qs = np.stack([quat.slerp(self.quaternion[i], self.quaternion[i + 1], float(si)) for i, si in zip(idx, s)])
        return pos, quat.make_continuous(qs)

    def evaluate_c2w(self, times, clamp: bool = False) -> np.ndarray:
        pos, qs = self.evaluate(times, clamp)
        return conventions.compose(pos, qs)

    def evaluate_lens(self, times, clamp: bool = False) -> np.ndarray | None:
        if self.lens_mm is None:
            return None
        idx, s = self._locate(_as_seconds(np.atleast_1d(times)), clamp)
        return self.lens_mm[idx] + (self.lens_mm[idx + 1] - self.lens_mm[idx]) * s

    def resample(self, times=None, rate: float | None = None) -> "CameraTrajectory":
        """New trajectory sampled at explicit times, or uniformly at `rate` Hz over the full range."""
        if times is None:
            if not rate or rate <= 0:
                raise ValueError("give times or a positive rate")
            n = max(2, int(round(self.duration * rate)) + 1)
            times = np.linspace(self.start, self.end, n)
        ts = _as_seconds(times)
        pos, qs = self.evaluate(ts)
        return CameraTrajectory(ts, pos, qs, self.evaluate_lens(ts), self.interpolation, dict(self.meta))

    # ------------------------------------------------------------------ persistence
    def save_npz(self, path: str | Path) -> None:
        arrays = {"t": self.t, "position": self.position, "quaternion_wxyz": self.quaternion,
                  "meta_json": np.array(json.dumps({"interpolation": self.interpolation, **self.meta}, sort_keys=True))}
        if self.lens_mm is not None:
            arrays["lens_mm"] = self.lens_mm
        np.savez_compressed(path, **arrays)

    @classmethod
    def load_npz(cls, path: str | Path, time_key: str = "t") -> "CameraTrajectory":
        with np.load(path, allow_pickle=False) as z:
            meta = json.loads(str(z["meta_json"])) if "meta_json" in z.files else {}
            interp = meta.pop("interpolation", "catmull_rom")
            t = z[time_key] if time_key in z.files else z["t_source"]
            return cls(t, z["position"], z["quaternion_wxyz"],
                       z["lens_mm"] if "lens_mm" in z.files else None, interp, meta)

    def arrays(self) -> dict[str, np.ndarray]:
        out = {"t": self.t, "position": self.position, "quaternion_wxyz": self.quaternion}
        if self.lens_mm is not None:
            out["lens_mm"] = self.lens_mm
        return out
