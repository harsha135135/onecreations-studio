"""Shared contract types: IDs, exact times, frame rates, hashes, matrices, rights and provenance."""

from __future__ import annotations

from fractions import Fraction
from typing import Annotated, Any, Literal

from pydantic import (AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer, PlainValidator,
                      WithJsonSchema)

from onecreations.timebase import FrameRate, format_time, parse_time

ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$"
Id = Annotated[str, Field(pattern=ID_PATTERN, max_length=128)]
"""Stable identifier, e.g. `hero_v4`, `temple_parry_004`, `fighter_A.sword` (dots address sub-parts)."""

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def _validate_time(value: Any) -> Fraction:
    try:
        return parse_time(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


RationalTime = Annotated[
    Fraction,
    PlainValidator(_validate_time),
    PlainSerializer(format_time, return_type=str),
    WithJsonSchema({"anyOf": [{"type": "string", "pattern": r"^\s*-?\d+(\.\d+)?(\s*/\s*\d+)?\s*$"},
                              {"type": "number"}],
                    "description": "Seconds, exact. Serialized as \"n/d\" (e.g. \"9/10\"); accepts numbers and decimals."}),
]
"""Exact seconds (fractions.Fraction). JSON: "9/10" or 0.9."""


def _non_negative(t: Fraction) -> Fraction:
    if t < 0:
        raise ValueError("time must be >= 0")
    return t


def _positive(t: Fraction) -> Fraction:
    if t <= 0:
        raise ValueError("duration must be > 0")
    return t


NonNegativeTime = Annotated[RationalTime, AfterValidator(_non_negative)]
PositiveDuration = Annotated[RationalTime, AfterValidator(_positive)]


def _check_matrix4(m: list[list[float]]) -> list[list[float]]:
    if len(m) != 4 or any(len(row) != 4 for row in m):
        raise ValueError("expected a 4x4 matrix (row-major)")
    return m


Matrix4 = Annotated[list[list[float]], AfterValidator(_check_matrix4)]
Vec3 = tuple[float, float, float]


class Model(BaseModel):
    """Base for all contracts: unknown fields are errors (catches typos in hand-written manifests)."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class FrameRateModel(Model):
    num: int = Field(gt=0)
    den: int = Field(default=1, gt=0)

    def to_rate(self) -> FrameRate:
        return FrameRate(self.num, self.den)


class FileRef(Model):
    role: str
    path: str
    sha256: Sha256 | None = None


class RightsRecord(Model):
    """Who owns an asset and what it may be used for (v1 §14). `ai_training_allowed` must be explicit."""
    owner: str
    license: str
    source_url: str | None = None
    license_snapshot_sha256: Sha256 | None = None
    allowed_uses: list[Literal["render", "training", "evaluation", "distribution", "reference"]] = Field(min_length=1)
    ai_training_allowed: bool
    consent_record: str | None = None
    notes: str | None = None


ProvenanceSource = Literal["authored", "blender_export", "colmap", "gyro", "csv", "retargeted", "procedural",
                           "mocap", "reference_footage"]
Confidence = Literal["verified_in_scene", "estimated", "inspired_by", "unknown"]


class Provenance(Model):
    source: ProvenanceSource
    confidence: Confidence = "unknown"
    parent: str | None = None
    notes: str | None = None
