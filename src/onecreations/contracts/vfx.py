"""VFX/audio event contract (v1 §11). Session A defines the schema; the event system is Session B."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from onecreations.contracts.common import Id, Model, NonNegativeTime, RationalTime


class EffectSpec(Model):
    """One effect of an event. Known fields are typed; preset-specific parameters are allowed as extras."""
    model_config = ConfigDict(extra="allow")
    preset: str | None = None
    asset: str | None = None
    duration_seconds: RationalTime | None = None
    offset_seconds: RationalTime | None = None


class VFXEvent(Model):
    """A deterministic, authored event in source time: the video model may add appearance, never timing."""
    schema_version: int = 1
    id: Id
    type: str = Field(description="e.g. SwordCollision, WallImpact")
    source_time_seconds: NonNegativeTime
    attachment: str | None = None
    participants: list[str] = []
    seed: int = 0
    effects: dict[str, EffectSpec] = {}
    cache_key_inputs: list[str] = []
