"""Camera motion asset contract (v1 §10 `camera_motion`)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from onecreations.contracts.common import Confidence, Id, Model, PositiveDuration, ProvenanceSource, Sha256


class CameraIntrinsicsModel(Model):
    """Blender perspective camera parameters (static over the motion; lens may additionally vary per sample)."""
    lens_mm: float = Field(gt=0)
    sensor_width_mm: float = Field(default=36.0, gt=0)
    sensor_height_mm: float = Field(default=24.0, gt=0)
    sensor_fit: Literal["AUTO", "HORIZONTAL", "VERTICAL"] = "AUTO"
    shift_x: float = 0.0
    shift_y: float = 0.0
    resolution_x: int = Field(default=1920, gt=0)
    resolution_y: int = Field(default=1080, gt=0)
    resolution_percentage: int = Field(default=100, gt=0)
    pixel_aspect_x: float = Field(default=1.0, gt=0)
    pixel_aspect_y: float = Field(default=1.0, gt=0)
    clip_start: float = Field(default=0.1, gt=0)
    clip_end: float = Field(default=1000.0, gt=0)
    K: list[list[float]] | None = Field(default=None, description="Derived 3x3 intrinsics (pixels, top-left origin)")


class CameraConstraints(Model):
    minimum_clearance_m: float = Field(default=0.0, ge=0)
    preserve_roll: bool = True
    max_angular_acceleration: float | Literal["artist_defined"] | None = None


class CameraProvenance(Model):
    source: ProvenanceSource
    confidence: Confidence = "unknown"
    scale: Literal["metric_verified", "metric_estimated", "unknown"] = "unknown"
    up_axis: Literal["aligned", "unaligned"] = "aligned"
    parent: str | None = None
    notes: str | None = None


class CameraMotion(Model):
    """Reusable camera move. Position and rotation are canonical; speed derives from path + time map."""
    schema_version: Literal[1] = 1
    id: Id
    units: Literal["meters"] = "meters"
    coordinate_system: Literal["blender_z_up"] = "blender_z_up"
    pose_convention: Literal["camera_to_world"] = "camera_to_world"
    rotation_format: Literal["quaternion_wxyz"] = "quaternion_wxyz"
    trajectory: str = Field(description="Samples file (.npz or .csv) relative to this manifest")
    trajectory_sha256: Sha256 | None = None
    intrinsics: CameraIntrinsicsModel | str = Field(description="Inline intrinsics or a relative JSON path")
    source_time_curve: str | None = None
    duration: PositiveDuration | None = Field(default=None, description="Source-time span; derived from samples if absent")
    target_bindings: list[str] = []
    constraints: CameraConstraints = CameraConstraints()
    provenance: CameraProvenance

    @model_validator(mode="after")
    def _trajectory_ext(self) -> "CameraMotion":
        if not self.trajectory.lower().endswith((".npz", ".csv")):
            raise ValueError("trajectory must be a .npz or .csv samples file")
        return self
