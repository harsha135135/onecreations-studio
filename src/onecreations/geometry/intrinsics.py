"""Blender perspective camera parameters → pinhole intrinsics, and projection.

Pixel convention: continuous image coordinates, origin at the **top-left corner** of the image, +u right, +v down;
pixel (col, row) covers [col, col+1) × [row, row+1), so its centre is (col + 0.5, row + 0.5).

Depth convention: **planar** view-space depth (distance along the optical axis, meters, positive in front).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from onecreations.geometry.conventions import FLIP_YZ, invert_rigid

SENSOR_FITS = ("AUTO", "HORIZONTAL", "VERTICAL")


@dataclass(frozen=True)
class BlenderCameraParams:
    lens_mm: float
    sensor_width_mm: float = 36.0
    sensor_height_mm: float = 24.0
    sensor_fit: str = "AUTO"
    shift_x: float = 0.0
    shift_y: float = 0.0
    resolution_x: int = 1920
    resolution_y: int = 1080
    resolution_percentage: int = 100
    pixel_aspect_x: float = 1.0
    pixel_aspect_y: float = 1.0
    clip_start: float = 0.1
    clip_end: float = 1000.0

    def __post_init__(self) -> None:
        if self.sensor_fit not in SENSOR_FITS:
            raise ValueError(f"sensor_fit must be one of {SENSOR_FITS}")
        if self.lens_mm <= 0 or self.sensor_width_mm <= 0 or self.sensor_height_mm <= 0:
            raise ValueError("lens and sensor sizes must be positive")
        if self.resolution_x <= 0 or self.resolution_y <= 0 or self.resolution_percentage <= 0:
            raise ValueError("resolution must be positive")
        if self.pixel_aspect_x <= 0 or self.pixel_aspect_y <= 0:
            raise ValueError("pixel aspect must be positive")

    @property
    def width_px(self) -> int:
        return int(self.resolution_x * self.resolution_percentage / 100)

    @property
    def height_px(self) -> int:
        return int(self.resolution_y * self.resolution_percentage / 100)

    def resolved_fit(self) -> str:
        if self.sensor_fit != "AUTO":
            return self.sensor_fit
        size_x = self.pixel_aspect_x * self.width_px
        size_y = self.pixel_aspect_y * self.height_px
        return "HORIZONTAL" if size_x >= size_y else "VERTICAL"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BlenderCameraParams":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in fields})


def intrinsic_matrix(p: BlenderCameraParams) -> np.ndarray:
    """3×3 K matching Blender's projection, including sensor fit, lens shift and non-square pixels."""
    w, h = float(p.width_px), float(p.height_px)
    # AUTO and HORIZONTAL both use the sensor *width* as the fitted size (Blender behaviour).
    sensor_size = p.sensor_height_mm if p.sensor_fit == "VERTICAL" else p.sensor_width_mm
    fit = p.resolved_fit()
    pixel_aspect_ratio = p.pixel_aspect_y / p.pixel_aspect_x
    view_fac = w if fit == "HORIZONTAL" else pixel_aspect_ratio * h
    mm_per_px = sensor_size / p.lens_mm / view_fac
    fx = 1.0 / mm_per_px
    fy = fx / pixel_aspect_ratio
    cx = w / 2.0 - p.shift_x * view_fac
    cy = h / 2.0 + p.shift_y * view_fac / pixel_aspect_ratio
    return np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]])


def world_to_camera_cv(points_world: np.ndarray, c2w: np.ndarray) -> np.ndarray:
    """(N,3) world points → (N,3) OpenCV camera coordinates (z = planar depth)."""
    pts = np.asarray(points_world, dtype=np.float64)
    w2c_cv = invert_rigid(np.asarray(c2w, dtype=np.float64) @ FLIP_YZ)
    return pts @ w2c_cv[:3, :3].T + w2c_cv[:3, 3]


def project(points_world: np.ndarray, c2w: np.ndarray, k: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Project world points with a Blender-convention c2w. Returns (uv (N,2) pixels, planar depth (N,)).

    Points behind the camera get depth ≤ 0 and meaningless uv; callers must mask them.
    """
    pc = world_to_camera_cv(points_world, c2w)
    z = pc[:, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        uvw = pc @ np.asarray(k, dtype=np.float64).T
        uv = uvw[:, :2] / uvw[:, 2:3]
    return uv, z


def pixel_rays_cv(uv: np.ndarray, k: np.ndarray) -> np.ndarray:
    """(N,2) pixels → (N,3) OpenCV-camera ray directions with z = 1 (not unit length)."""
    uv = np.asarray(uv, dtype=np.float64)
    kinv = np.linalg.inv(np.asarray(k, dtype=np.float64))
    ones = np.ones((uv.shape[0], 1))
    return np.hstack([uv, ones]) @ kinv.T


def unproject(uv: np.ndarray, depth: np.ndarray, c2w: np.ndarray, k: np.ndarray) -> np.ndarray:
    """Pixels + planar depth → world points."""
    rays = pixel_rays_cv(uv, k) * np.asarray(depth, dtype=np.float64)[:, None]
    c2w_cv = np.asarray(c2w, dtype=np.float64) @ FLIP_YZ
    return rays @ c2w_cv[:3, :3].T + c2w_cv[:3, 3]


def pixel_centers(width: int, height: int) -> np.ndarray:
    """(H, W, 2) array of (u, v) pixel-centre coordinates, rows top-down."""
    us = np.arange(width) + 0.5
    vs = np.arange(height) + 0.5
    uu, vv = np.meshgrid(us, vs)
    return np.stack([uu, vv], axis=-1)


def euclidean_to_planar_factor(width: int, height: int, k: np.ndarray) -> np.ndarray:
    """(H, W) factor f with planar_depth = euclidean_distance × f (cosine of the ray angle)."""
    uv = pixel_centers(width, height).reshape(-1, 2)
    rays = pixel_rays_cv(uv, k)
    f = 1.0 / np.linalg.norm(rays, axis=1)
    return f.reshape(height, width)


def frustum_corners_world(c2w: np.ndarray, k: np.ndarray, width: int, height: int, depth: float) -> np.ndarray:
    """(4,3) world-space image-corner points at planar `depth`, order: TL, TR, BR, BL."""
    corners = np.array([[0.0, 0.0], [width, 0.0], [width, height], [0.0, height]])
    return unproject(corners, np.full(4, float(depth)), c2w, k)
