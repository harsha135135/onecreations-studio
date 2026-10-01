"""Shot package contract (v1 §13): the central editable object, not a prompt."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from onecreations.contracts.common import FrameRateModel, Id, Model, NonNegativeTime, PositiveDuration

ControlModality = Literal["depth", "pose", "edges", "normal", "mask", "first_frame", "last_frame", "keyframes",
                          "reference_image", "camera_matrices", "plucker_rays", "optical_flow"]


class GenerationSpec(Model):
    backend_profile: Id
    allowed_regions: list[Id] = []
    protected_regions: list[Id] = []
    controls: list[ControlModality] = []
    reference_count: int = Field(default=0, ge=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)


class Shot(Model):
    schema_version: Literal[1] = 1
    id: Id
    scene_state_in: Id
    duration_seconds: PositiveDuration
    output_fps: FrameRateModel
    source_start: NonNegativeTime = Field(default=0, description="Choreography source time at output time 0 "
                                                                  "(used when no timewarp is given)")
    assets: list[Id] = Field(min_length=1)
    choreography: Id
    camera: Id
    timewarp: Id | None = None
    lighting: Id | None = None
    references: list[Id] = []
    generation: GenerationSpec | None = None
    events: list[Id] = []
    continuity_out: Id | None = None
    acceptance: Id | None = None

    @model_validator(mode="after")
    def _unique(self) -> "Shot":
        for label, items in (("assets", self.assets), ("events", self.events), ("references", self.references)):
            dupes = sorted({i for i in items if items.count(i) > 1})
            if dupes:
                raise ValueError(f"duplicate {label}: {dupes}")
        return self
