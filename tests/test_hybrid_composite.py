from fractions import Fraction

import numpy as np
import pytest

from tools.admission import hybrid_composite as hc


def test_alpha_over_and_gain():
    base = np.full((2, 2, 3), 100, np.uint8)
    layer = np.zeros((2, 2, 4), np.uint8)
    layer[0, 0] = (200, 100, 50, 255)          # opaque
    layer[0, 1] = (200, 100, 50, 128)          # ~half
    out = hc.alpha_over(base, layer)
    assert out[0, 0].tolist() == [200, 100, 50] and out[1, 1].tolist() == [100, 100, 100]
    assert out[0, 1].tolist() == [150, 100, 75]
    graded = hc.alpha_over(base, layer, gain=(0.5, 1.0, 2.0))
    assert graded[0, 0].tolist() == [100, 100, 100]


def test_fit_gain_median_and_clip():
    lay = np.full((50, 3), 100.0)
    pairs = [(np.full((50, 3), [120.0, 90.0, 300.0]), lay), (np.full((50, 3), [110.0, 80.0, 300.0]), lay)]
    assert hc.fit_gain(pairs) == [1.15, 0.85, 1.6]                     # blue clipped to 1.6
    assert hc.fit_gain([(np.zeros((5, 3)), np.ones((5, 3)))]) == [1.0, 1.0, 1.0]   # too few samples -> identity


def test_inpaint_fills_from_surroundings():
    img = np.zeros((20, 20, 3), np.uint8)
    img[:, :10] = 40
    img[:, 10:] = 200
    hole = np.zeros((20, 20), bool)
    hole[8:12, 3:6] = True                    # inside the dark half
    img[hole] = 255                           # a bright "ghost" to remove
    out = hc.inpaint(img, hole)
    assert np.abs(out[hole].astype(int) - 40).max() <= 2
    assert np.array_equal(out[~hole], img[~hole])


def test_authored_protection_trigger_and_attachment():
    cents = [(100.0, 50.0 + v) for v in (0, 0, 2, 30, 90, 150, 155, 155, 155)]
    widths = [50] * len(cents)
    # steps 0, 2, 28, 60, 60, 5, 0, 0 px; a frame is fast when its step in or out is >= 0.5 x 50 px
    assert hc.authored_fast_frames(cents, widths, 0.5, 0) == [2, 3, 4, 5]
    assert hc.authored_fast_frames(cents, widths, 0.5, 1) == [1, 2, 3, 4, 5, 6]
    tl = {"phases": [{"id": "impact", "start": "29/24", "end": "17/12"}]}
    assert hc.trigger_frame(tl, "impact", "start", Fraction(24)) == 29
    assert hc.trigger_frame(tl, "impact", "end", Fraction(24)) == 34
    with pytest.raises(ValueError):
        hc.trigger_frame({"phases": [{"id": "x", "start": "1/48"}]}, "x", "start", Fraction(24))
    mask = np.zeros((50, 50), bool)
    mask[20, 30] = True
    assert hc.nearest_distance((26.0, 20.0), mask) == 4.0
    assert hc.nearest_distance((0.0, 0.0), np.zeros((50, 50), bool)) is None


def test_additive_light_pass():
    base = np.full((1, 2, 3), 200, np.uint8)
    light = np.zeros((1, 2, 4), np.uint8)
    light[0, 0] = (40, 80, 120, 255)
    out = hc.apply_effect(base, light, "add")
    assert out[0, 0].tolist() == [240, 255, 255] and out[0, 1].tolist() == [200, 200, 200]   # clipped at 255
    assert hc.apply_effect(base, light, "over")[0, 0].tolist() == [40, 80, 120]


def test_soften_premultiplied_keeps_colour_and_spreads_alpha():
    layer = np.zeros((9, 9, 4), np.uint8)
    layer[4, 4] = (200, 100, 50, 255)
    out = hc.soften(layer, 1.0)
    assert out[4, 4, 3] < 255 and out[4, 5, 3] > 0 and out[0, 0, 3] == 0
    assert out[4, 5, :3].tolist() == [200, 100, 50]            # no dark fringe: colour kept where alpha spreads
    assert np.array_equal(hc.soften(layer, 0.0), layer)


def test_protection_rule_ghost_frames_default_and_all():
    """D3: ghost suppression defaults to the unreliable (authored-fast / low-retention) frames, as in M3-A / Showcase /
    D2; contact_weapon_v1 asks for every protected frame (a long thin weapon is never 'fast' in its own widths)."""
    from onecreations.contracts.composite import ProtectionRule
    assert ProtectionRule(track_object="sc_mace_head").ghost_frames == "unreliable"
    assert ProtectionRule(track_object="sc_trident", ghost_frames="all").ghost_frames == "all"
    with pytest.raises(ValueError):
        ProtectionRule(track_object="sc_trident", ghost_frames="some")
