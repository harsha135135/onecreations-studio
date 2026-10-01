"""Exact time arithmetic for shots, events and time maps (v1 §13).

All times are `fractions.Fraction` seconds. 0.90 s stays 9/10 s, so an event at 0.90 s in a 24 fps shot sits at
output frame position 21.6 exactly; each subsystem samples that same value instead of rounding independently.

Stdlib only: this module is imported by Blender-side scripts as well as the main package.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Iterable, Sequence, Union

TimeLike = Union[Fraction, int, float, str, Decimal]


def parse_time(value: TimeLike) -> Fraction:
    """Parse seconds exactly: Fraction, int, "9/10", "0.90", Decimal, or a float via its shortest repr (0.9 → 9/10)."""
    if isinstance(value, bool):
        raise TypeError("bool is not a time")
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite time {value!r}")
        return Fraction(Decimal(repr(value)))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"non-finite time {value!r}")
        return Fraction(value)
    if isinstance(value, str):
        s = value.strip()
        try:
            if "/" in s:
                num, den = s.split("/", 1)
                return Fraction(int(num.strip()), int(den.strip()))
            return Fraction(Decimal(s))
        except (ValueError, ZeroDivisionError, InvalidOperation) as exc:
            raise ValueError(f"cannot parse time {value!r}") from exc
    raise TypeError(f"unsupported time type {type(value).__name__}")


def format_time(t: Fraction) -> str:
    """Canonical string form: "9/10", "6", "-1/24"."""
    t = Fraction(t)
    return str(t.numerator) if t.denominator == 1 else f"{t.numerator}/{t.denominator}"


@dataclass(frozen=True)
class FrameRate:
    num: int
    den: int = 1

    def __post_init__(self) -> None:
        if self.num <= 0 or self.den <= 0:
            raise ValueError(f"frame rate must be positive, got {self.num}/{self.den}")

    @classmethod
    def from_value(cls, value: "FrameRate | dict | TimeLike") -> "FrameRate":
        if isinstance(value, FrameRate):
            return value
        if isinstance(value, dict):
            return cls(int(value["num"]), int(value.get("den", 1)))
        f = parse_time(value)
        return cls(f.numerator, f.denominator)

    @property
    def fps(self) -> Fraction:
        return Fraction(self.num, self.den)

    @property
    def frame_duration(self) -> Fraction:
        return Fraction(self.den, self.num)

    def time_of_frame(self, k: int) -> Fraction:
        return Fraction(k * self.den, self.num)

    def frame_position(self, t: TimeLike) -> Fraction:
        """Exact (possibly fractional) frame position of time t: 0.9 s @ 24 fps → 108/5 (= 21.6)."""
        return parse_time(t) * self.fps

    def nearest_frame(self, t: TimeLike) -> int:
        """Nearest frame index, halves rounded up."""
        return math.floor(self.frame_position(t) + Fraction(1, 2))

    def frame_count(self, duration: TimeLike) -> Fraction:
        """duration × fps; an integer Fraction when the duration is a whole number of frames."""
        return parse_time(duration) * self.fps

    def frame_times(self, count: int) -> list[Fraction]:
        return [self.time_of_frame(k) for k in range(count)]

    def to_dict(self) -> dict:
        return {"num": self.num, "den": self.den}


class TimeWarp:
    """Monotonic piecewise-linear map from output time to source (action) time.

    keys: [(output_t, source_t), ...] with output strictly increasing and source non-decreasing.
    A flat segment is a hold (freeze): `inverse` then returns the earliest output time.
    Evaluating outside the key range raises; a time map must cover the whole shot explicitly.
    """

    __slots__ = ("keys",)

    def __init__(self, keys: Iterable[Sequence[TimeLike]]):
        parsed = [(parse_time(o), parse_time(s)) for o, s in keys]
        if len(parsed) < 2:
            raise ValueError("a TimeWarp needs at least two keys")
        for (o0, s0), (o1, s1) in zip(parsed, parsed[1:]):
            if o1 <= o0:
                raise ValueError(f"output times must strictly increase ({format_time(o0)} → {format_time(o1)})")
            if s1 < s0:
                raise ValueError(f"source times must not decrease ({format_time(s0)} → {format_time(s1)})")
        self.keys: tuple[tuple[Fraction, Fraction], ...] = tuple(parsed)

    @classmethod
    def identity(cls, duration: TimeLike, source_start: TimeLike = 0) -> "TimeWarp":
        d, s = parse_time(duration), parse_time(source_start)
        return cls([(0, s), (d, s + d)])

    @property
    def output_start(self) -> Fraction:
        return self.keys[0][0]

    @property
    def output_end(self) -> Fraction:
        return self.keys[-1][0]

    @property
    def source_start(self) -> Fraction:
        return self.keys[0][1]

    @property
    def source_end(self) -> Fraction:
        return self.keys[-1][1]

    def covers_output(self, start: TimeLike, end: TimeLike) -> bool:
        return self.output_start <= parse_time(start) and parse_time(end) <= self.output_end

    def __call__(self, output_t: TimeLike) -> Fraction:
        t = parse_time(output_t)
        if t < self.output_start or t > self.output_end:
            raise ValueError(f"output time {format_time(t)} outside time map "
                             f"[{format_time(self.output_start)}, {format_time(self.output_end)}]")
        for (o0, s0), (o1, s1) in zip(self.keys, self.keys[1:]):
            if t <= o1:
                return s0 + (s1 - s0) * (t - o0) / (o1 - o0)
        raise AssertionError("unreachable")

    def inverse(self, source_t: TimeLike) -> Fraction:
        """Earliest output time whose source time equals source_t."""
        s = parse_time(source_t)
        if s < self.source_start or s > self.source_end:
            raise ValueError(f"source time {format_time(s)} outside time map "
                             f"[{format_time(self.source_start)}, {format_time(self.source_end)}]")
        for (o0, s0), (o1, s1) in zip(self.keys, self.keys[1:]):
            if s <= s1:
                if s1 == s0:
                    return o0
                return o0 + (o1 - o0) * (s - s0) / (s1 - s0)
        raise AssertionError("unreachable")

    def speed(self, output_t: TimeLike) -> Fraction:
        """ds/do on the segment containing output_t (right-continuous; last segment at the end)."""
        t = parse_time(output_t)
        for (o0, s0), (o1, s1) in zip(self.keys, self.keys[1:]):
            if t < o1 or o1 == self.output_end:
                return (s1 - s0) / (o1 - o0)
        raise AssertionError("unreachable")

    def to_dict(self) -> dict:
        return {"keys": [[format_time(o), format_time(s)] for o, s in self.keys]}

    @classmethod
    def from_dict(cls, data: dict) -> "TimeWarp":
        return cls(data["keys"])

    def __eq__(self, other: object) -> bool:
        return isinstance(other, TimeWarp) and self.keys == other.keys

    def __hash__(self) -> int:
        return hash(self.keys)

    def __repr__(self) -> str:
        return f"TimeWarp({self.to_dict()['keys']})"
