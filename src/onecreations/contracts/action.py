"""Choreography (action timeline) and time-map contracts (v1 §10, §13). All times are source (action) time."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from onecreations.contracts.common import Id, Model, NonNegativeTime, PositiveDuration, RationalTime
from onecreations.timebase import TimeWarp

PhaseKind = Literal["advance", "strike", "defense", "contact", "recoil", "counterattack", "dodge", "throw", "impact",
                    "hold", "recovery", "idle", "other"]


class Phase(Model):
    id: Id
    kind: PhaseKind
    actor: str = Field(description="Actor role, e.g. fighter_A")
    start: NonNegativeTime
    end: NonNegativeTime

    @model_validator(mode="after")
    def _order(self) -> "Phase":
        if self.end < self.start:
            raise ValueError(f"phase {self.id}: end before start")
        return self


class ContactInterval(Model):
    """An authored contact: e.g. blade-on-blade between fighter_A.sword and fighter_B.sword."""
    id: Id
    participants: list[str] = Field(min_length=2, description="role.part references, e.g. fighter_A.sword")
    start: NonNegativeTime
    end: NonNegativeTime
    contact_points: list[str] = Field(default=[], description="e.g. fighter_A.sword.tip")
    required: bool = True
    event: Id | None = Field(default=None, description="VFX/audio event triggered by this contact")

    @model_validator(mode="after")
    def _order(self) -> "ContactInterval":
        if self.end < self.start:
            raise ValueError(f"contact {self.id}: end before start")
        return self


class ActionTimeline(Model):
    """Choreography in source time. `actors` binds roles to asset IDs so motion survives character swaps."""
    schema_version: Literal[1] = 1
    id: Id
    version: str
    duration: PositiveDuration
    actors: dict[str, Id] = Field(min_length=1, description="role → asset id, e.g. {fighter_A: hero_v4}")
    phases: list[Phase] = []
    contacts: list[ContactInterval] = []

    @model_validator(mode="after")
    def _checks(self) -> "ActionTimeline":
        for ph in self.phases:
            if ph.actor not in self.actors:
                raise ValueError(f"phase {ph.id}: unknown actor role {ph.actor!r}")
            if ph.end > self.duration:
                raise ValueError(f"phase {ph.id}: ends after the timeline duration")
        for c in self.contacts:
            if c.end > self.duration:
                raise ValueError(f"contact {c.id}: ends after the timeline duration")
            for ref in c.participants + c.contact_points:
                role = ref.split(".", 1)[0]
                if role not in self.actors:
                    raise ValueError(f"contact {c.id}: {ref!r} does not start with a known actor role")
        ids = [p.id for p in self.phases] + [c.id for c in self.contacts]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate phase/contact ids: {dupes}")
        return self


class TimeWarpModel(Model):
    """Output time → source time map (monotonic piecewise-linear; holds allowed)."""
    schema_version: Literal[1] = 1
    id: Id
    description: str | None = None
    keys: list[tuple[RationalTime, RationalTime]] = Field(min_length=2)

    @model_validator(mode="after")
    def _monotonic(self) -> "TimeWarpModel":
        TimeWarp(self.keys)  # raises ValueError with a precise message
        return self

    def to_timewarp(self) -> TimeWarp:
        return TimeWarp(self.keys)
