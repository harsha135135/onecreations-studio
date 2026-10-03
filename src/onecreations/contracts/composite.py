"""Composite layer manifest (M3-A on): deterministic layers rendered from the authored Blender scene and combined
with a generated video. Blender owns geometry, camera, timing and weapon transform; the generated video owns
appearance; the compositor protects critical geometry and adds deterministic effects at authored times."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from onecreations.contracts.common import Id, Model


class LayerRender(Model):
    """How render_layers.py renders a layer: listed objects/collections visible, every other mesh a holdout (it
    still occludes and casts shadows but renders as transparent), transparent film, optional Blender motion blur."""
    holdout_others: bool = True
    motion_blur_shutter: float | None = Field(default=0.5, gt=0, le=1, description="frames; 0.5 = 180 deg shutter")
    samples: int = Field(default=64, gt=0)


class LayerTrigger(Model):
    """An effect starts at an ActionTimeline phase boundary (never chosen by the generative model)."""
    timeline: Id
    phase: Id
    edge: Literal["start", "end"] = "start"


class ProtectionRule(Model):
    """Which output frames a protected-geometry layer replaces. Union of: frames where the authored speed of the
    tracked object (into or out of the frame) is >= authored_speed_widths x its own width (from ground truth),
    dilated by dilate_frames; and frames where the raw generated retention (vs the matched motion-blur reference) is
    below raw_retention_below."""
    track_object: str
    authored_speed_widths: float | None = Field(default=None, gt=0)
    dilate_frames: int = Field(default=1, ge=0)
    raw_retention_below: float | None = Field(default=None, gt=0, le=1)


class CompositeLayer(Model):
    id: Id
    kind: Literal["protected_geometry", "effect"]
    objects: list[str] = Field(default=[], description="oc_ids rendered visible in this layer")
    collections: list[str] = Field(default=[], description="view-layer collections enabled for this layer only")
    render: LayerRender = LayerRender()
    occlusion: Literal["holdout"] = "holdout"
    order: int = Field(default=0, description="compositing order (lower first)")
    protection: ProtectionRule | None = None
    trigger: LayerTrigger | None = None
    duration_frames: int | None = Field(default=None, gt=0)
    grade: Literal["none", "per_channel_gain"] = "none"
    ghost_suppression: bool = Field(default=False, description="inpaint raw generated remnants of the protected "
                                                               "object near its authored path in protected frames")

    @model_validator(mode="after")
    def _kind_fields(self) -> "CompositeLayer":
        if not self.objects and not self.collections:
            raise ValueError(f"layer {self.id}: nothing to render")
        if self.kind == "protected_geometry" and self.protection is None:
            raise ValueError(f"layer {self.id}: protected geometry needs a protection rule")
        if self.kind == "effect" and (self.trigger is None or self.duration_frames is None):
            raise ValueError(f"layer {self.id}: an effect needs a trigger and a duration")
        return self


class CompositeManifest(Model):
    schema_version: Literal[1] = 1
    id: Id
    shot: str
    layers: list[CompositeLayer] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> "CompositeManifest":
        ids = [ly.id for ly in self.layers]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate layer ids: {ids}")
        return self
