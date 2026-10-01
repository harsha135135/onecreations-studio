"""Camera and world axis conventions.

Canonical OneCreations pose: **camera_to_world** 4×4 in **Blender camera axes** — camera looks along −Z, +Y is up,
+X is right; world is Blender Z-up, right-handed, meters.

- OpenCV / COLMAP camera axes: +Z forward, +Y down, +X right → c2w_cv = c2w_blender · diag(1, −1, −1, 1).
- OpenGL camera axes equal Blender camera axes (−Z forward, +Y up); only world up may differ (Y-up worlds).
"""

from __future__ import annotations

import numpy as np

from onecreations.geometry import quat

FLIP_YZ = np.diag([1.0, -1.0, -1.0, 1.0])

# Blender Z-up world → Y-up world (x, y, z) → (x, z, −y)
WORLD_ZUP_TO_YUP = np.array([
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, -1.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
])


class ConventionError(ValueError):
    """A pose matrix violates the canonical convention (not rigid, reflected, or malformed)."""


def validate_rigid(m: np.ndarray, tol: float = 1e-6) -> np.ndarray:
    """Return m as float64 (…,4,4) or raise if any matrix is not a proper rigid transform.

    Catches flipped axes (det = −1), scale/shear, and bad bottom rows.
    """
    m = np.asarray(m, dtype=np.float64)
    if m.shape[-2:] != (4, 4):
        raise ConventionError(f"expected (...,4,4), got {m.shape}")
    r = m[..., :3, :3]
    if not np.all(np.isfinite(m)):
        raise ConventionError("non-finite values in pose")
    if not np.allclose(m[..., 3, :], [0.0, 0.0, 0.0, 1.0], atol=tol):
        raise ConventionError("bottom row must be [0, 0, 0, 1]")
    eye = np.broadcast_to(np.eye(3), r.shape)
    if not np.allclose(r @ np.swapaxes(r, -1, -2), eye, atol=tol):
        raise ConventionError("rotation block is not orthonormal (scale or shear present)")
    det = np.linalg.det(r)
    if np.any(det < 0):
        raise ConventionError("rotation has det −1: an axis is flipped (mirror), not a proper rotation")
    return m


def invert_rigid(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float64)
    r, t = m[..., :3, :3], m[..., :3, 3]
    out = np.zeros_like(m)
    rt = np.swapaxes(r, -1, -2)
    out[..., :3, :3] = rt
    out[..., :3, 3] = -np.einsum("...ij,...j->...i", rt, t)
    out[..., 3, 3] = 1.0
    return out


def blender_c2w_to_opencv(c2w: np.ndarray) -> np.ndarray:
    return np.asarray(c2w, dtype=np.float64) @ FLIP_YZ


def opencv_c2w_to_blender(c2w_cv: np.ndarray) -> np.ndarray:
    return np.asarray(c2w_cv, dtype=np.float64) @ FLIP_YZ


def compose(position, quat_wxyz) -> np.ndarray:
    """(…,3) + (…,4) → (…,4,4) camera_to_world."""
    position = np.asarray(position, dtype=np.float64)
    r = quat.to_matrix(quat_wxyz)
    m = np.zeros(position.shape[:-1] + (4, 4))
    m[..., :3, :3] = r
    m[..., :3, 3] = position
    m[..., 3, 3] = 1.0
    return m


def decompose(c2w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(4,4) rigid → (position (3,), quaternion wxyz (4,))."""
    m = validate_rigid(c2w)
    return m[:3, 3].copy(), quat.from_matrix(m[:3, :3])


def camera_forward(c2w: np.ndarray) -> np.ndarray:
    return -np.asarray(c2w)[..., :3, 2]


def camera_up(c2w: np.ndarray) -> np.ndarray:
    return np.asarray(c2w)[..., :3, 1]


def look_at(eye, target, world_up=(0.0, 0.0, 1.0), roll_rad: float = 0.0) -> np.ndarray:
    """Blender-convention camera_to_world looking from eye to target.

    Positive roll turns the camera's right axis toward its up axis (counter-clockwise seen from behind the camera),
    so image content appears rotated clockwise. `roll_angle` returns the same value.
    """
    eye, target, up = (np.asarray(v, dtype=np.float64) for v in (eye, target, world_up))
    fwd = target - eye
    n = np.linalg.norm(fwd)
    if n < 1e-12:
        raise ValueError("eye and target coincide")
    fwd /= n
    right = np.cross(fwd, up)
    if np.linalg.norm(right) < 1e-9:
        raise ValueError("forward is parallel to world_up; roll is undefined")
    right /= np.linalg.norm(right)
    cam_up = np.cross(right, fwd)
    if roll_rad:
        c, s = np.cos(roll_rad), np.sin(roll_rad)
        right, cam_up = c * right + s * cam_up, -s * right + c * cam_up
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = right, cam_up, -fwd, eye
    return m


def roll_angle(c2w: np.ndarray, world_up=(0.0, 0.0, 1.0)) -> np.ndarray:
    """Camera roll (radians) relative to world up; NaN when looking (nearly) straight up or down."""
    c2w = np.asarray(c2w, dtype=np.float64)
    up = np.asarray(world_up, dtype=np.float64)
    r = c2w[..., :3, :3]
    up_cam = np.einsum("...ji,j->...i", r, up)  # world up expressed in camera axes (R^T up)
    horiz = np.hypot(up_cam[..., 0], up_cam[..., 1])
    roll = np.arctan2(up_cam[..., 0], up_cam[..., 1])
    return np.where(horiz > 1e-6, roll, np.nan)
