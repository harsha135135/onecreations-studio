"""Unit quaternions in (w, x, y, z) order, float64. Rotation of vectors is active: v' = q v q*."""

from __future__ import annotations

import numpy as np

EPS = 1e-12


def normalize(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64)
    n = np.linalg.norm(q, axis=-1, keepdims=True)
    if np.any(n < EPS):
        raise ValueError("zero-length quaternion")
    return q / n


def multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    aw, ax, ay, az = np.moveaxis(a, -1, 0)
    bw, bx, by, bz = np.moveaxis(b, -1, 0)
    return np.stack([
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ], axis=-1)


def conjugate(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64)
    return q * np.array([1.0, -1.0, -1.0, -1.0])


def from_axis_angle(axis, angle_rad: float) -> np.ndarray:
    axis = np.asarray(axis, dtype=np.float64)
    n = np.linalg.norm(axis)
    if n < EPS:
        raise ValueError("zero-length axis")
    axis = axis / n
    half = 0.5 * angle_rad
    return np.concatenate([[np.cos(half)], np.sin(half) * axis])


def to_matrix(q: np.ndarray) -> np.ndarray:
    """(…,4) → (…,3,3) rotation matrices."""
    w, x, y, z = np.moveaxis(normalize(q), -1, 0)
    m = np.stack([
        1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y),
        2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x),
        2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y),
    ], axis=-1)
    return m.reshape(m.shape[:-1] + (3, 3))


def from_matrix(m: np.ndarray) -> np.ndarray:
    """(3,3) proper rotation → unit quaternion with w ≥ 0 (Shepperd's method)."""
    m = np.asarray(m, dtype=np.float64)
    if m.shape != (3, 3):
        raise ValueError(f"expected (3,3), got {m.shape}")
    tr = np.trace(m)
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    else:
        s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    q = normalize(np.array(q))
    return -q if q[0] < 0 else q


def rotate(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    return np.asarray(v, dtype=np.float64) @ to_matrix(q).swapaxes(-1, -2)


def make_continuous(qs: np.ndarray) -> np.ndarray:
    """Flip signs so consecutive quaternions lie in the same hemisphere (q and −q are the same rotation)."""
    qs = np.array(qs, dtype=np.float64, copy=True)
    for i in range(1, len(qs)):
        if np.dot(qs[i], qs[i - 1]) < 0:
            qs[i] = -qs[i]
    return qs


def slerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    """Shortest-path spherical interpolation; t in [0, 1]."""
    a, b = normalize(a), normalize(b)
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > 1 - 1e-12:
        return normalize(a + t * (b - a))
    theta = np.arccos(np.clip(d, -1.0, 1.0))
    s = np.sin(theta)
    return (np.sin((1 - t) * theta) / s) * a + (np.sin(t * theta) / s) * b


def angle_between(a: np.ndarray, b: np.ndarray) -> float:
    """Rotation angle (radians, 0..π) taking a to b. atan2 form stays accurate for tiny angles."""
    rel = multiply(conjugate(normalize(a)), normalize(b))
    return 2.0 * float(np.arctan2(np.linalg.norm(rel[1:]), abs(rel[0])))
