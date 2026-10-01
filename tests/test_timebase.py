from fractions import Fraction

import pytest

from onecreations.timebase import FrameRate, TimeWarp, format_time, parse_time


@pytest.mark.parametrize("value,expected", [
    (0.9, Fraction(9, 10)), ("0.90", Fraction(9, 10)), ("9/10", Fraction(9, 10)), (6, Fraction(6)),
    (0.45, Fraction(9, 20)), (" 1/24 ", Fraction(1, 24)), (Fraction(3, 7), Fraction(3, 7)),
])
def test_parse_time_is_exact(value, expected):
    assert parse_time(value) == expected


@pytest.mark.parametrize("bad", ["abc", "1/0", float("nan"), True])
def test_parse_time_rejects(bad):
    with pytest.raises((ValueError, TypeError)):
        parse_time(bad)


def test_contact_at_0_90s_is_subframe_21_6_at_24fps():
    fr = FrameRate(24)
    pos = fr.frame_position("0.90")
    assert pos == Fraction(108, 5) and float(pos) == 21.6
    assert fr.nearest_frame("0.90") == 22
    assert fr.frame_count(6) == 144


def test_ntsc_rate_is_exact():
    fr = FrameRate(24000, 1001)
    assert fr.time_of_frame(24000) == 1001
    assert fr.frame_position(fr.time_of_frame(17)) == 17
    assert format_time(fr.time_of_frame(1)) == "1001/24000"


def test_timewarp_roundtrip_and_hold():
    # 0-1 s normal, 1-2 s hold at source 1.0 (impact hold), 2-3 s 2x speed
    tw = TimeWarp([(0, 0), (1, 1), (2, 1), (3, 3)])
    assert tw("1/2") == Fraction(1, 2)
    assert tw("1.5") == 1  # held
    assert tw("2.5") == 2
    assert tw.inverse(1) == 1  # earliest output time in the hold
    assert tw.inverse(2) == Fraction(5, 2)
    for k in range(0, 73):
        t = Fraction(k, 24)
        if not (1 < t <= 2):  # outside the hold, inverse(forward(t)) == t
            assert tw.inverse(tw(t)) == t
    assert tw.speed("1.5") == 0 and tw.speed("2.5") == 2


def test_timewarp_rejects_non_monotonic_and_out_of_range():
    with pytest.raises(ValueError):
        TimeWarp([(0, 0), (1, 2), (2, 1)])
    with pytest.raises(ValueError):
        TimeWarp([(0, 0), (0, 1)])
    tw = TimeWarp.identity(2)
    with pytest.raises(ValueError):
        tw("2.01")
    assert TimeWarp.from_dict(tw.to_dict()) == tw
