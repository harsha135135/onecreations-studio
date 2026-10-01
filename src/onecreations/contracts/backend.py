"""Model backend profile (v1 §28): what a backend actually supports, so unsupported requests fail loudly.

Values for real models are filled from measured admission runs and pinned upstream docs, never assumed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from onecreations.contracts.common import Id, Model
from onecreations.contracts.shot import ControlModality

Task = Literal["t2v", "i2v", "v2v_control", "inpaint", "outpaint", "reference_edit", "keyframe_interp", "t2i",
               "image_edit"]
AdmissionStatus = Literal["not_run", "A_admitted", "B_preview_only", "C_not_admitted"]


class FrameCountRule(Model):
    """Allowed frame counts: count = multiple·n + remainder (n ≥ 1), within [min_frames, max_frames]."""
    multiple: int = Field(default=1, gt=0)
    remainder: int = Field(default=0, ge=0)
    min_frames: int = Field(default=1, gt=0)
    max_frames: int | None = Field(default=None, gt=0)

    def allows(self, count: int) -> bool:
        if count < self.min_frames or (self.max_frames is not None and count > self.max_frames):
            return False
        return count >= self.remainder and (count - self.remainder) % self.multiple == 0


class BackendAdmission(Model):
    status: AdmissionStatus = "not_run"
    envelope: str | None = None
    records: list[str] = []


class ModelBackend(Model):
    schema_version: Literal[1] = 1
    id: Id
    model_id: str = Field(description="model_registry id")
    runtime: str = Field(description="e.g. comfyui@<sha> + workflow name")
    tasks: list[Task] = Field(min_length=1)
    control_modalities: list[ControlModality] = []
    max_reference_images: int = Field(default=0, ge=0)
    width_multiple: int = Field(default=1, gt=0)
    height_multiple: int = Field(default=1, gt=0)
    max_width: int | None = Field(default=None, gt=0)
    max_height: int | None = Field(default=None, gt=0)
    frame_count: FrameCountRule = FrameCountRule()
    accepts_camera_matrices: bool = False
    mask_behavior: Literal["none", "soft", "hard"] = "none"
    audio: Literal["none", "generates", "conditions"] = "none"
    adapter_compat: list[str] = []
    admission: BackendAdmission = BackendAdmission()
    notes: str | None = None
