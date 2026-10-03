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


# --- M3-B hybrid v2 (fill_under_layer): deterministic reference cases, written before the M3-B generation ----------

GOLD, SMEAR, CRIMSON = (200, 140, 30), (170, 130, 95), (150, 30, 25)   # SMEAR matches no colour rule


def _v2_scene():
    """A synthetic protected frame. Background: a smooth gradient. Authored layer: an opaque gold head (alpha 255) with
    a semi-transparent motion-blur streak behind it (alpha 100) and a holdout hole where an actor is in front of the
    weapon (alpha 0). Raw generated frame: the background plus the known M3-A failure, a raw gold blob and a
    desaturated smear that no colour rule detects UNDER the streak (double-image sources), a stray gold remnant just
    outside the layer, the generated hand under the streak (crimson, must show through) and the occluding actor."""
    h, w = 80, 240
    yy, xx = np.mgrid[0:h, 0:w]
    bg = np.stack([60 + xx * 0.25, 58 + yy * 0.3, 55 + 0 * xx], -1).astype(np.uint8)
    layer = np.zeros((h, w, 4), np.uint8)
    layer[30:50, 180:200] = (*GOLD, 255)                 # solid head
    layer[34:46, 40:180] = (*GOLD, 100)                  # blur streak (partial alpha)
    occluder = np.zeros((h, w), bool)
    occluder[30:50, 120:128] = True                      # actor in front of the weapon: holdout -> alpha 0
    layer[occluder] = 0
    actors = bg.copy()
    actors[37:43, 92:98] = CRIMSON                       # generated hand under the streak (kept)
    actors[occluder] = CRIMSON                           # generated actor in front of the weapon
    raw = actors.copy()
    raw[36:44, 45:60] = GOLD                             # raw blob under the streak (gold rule)
    raw[36:44, 150:162] = SMEAR                          # raw smear under the streak (no colour rule fires)
    raw[52:56, 184:196] = GOLD                           # stray remnant below the head, outside the layer
    band = np.zeros((h, w), bool)
    band[20:62, 30:210] = True
    truth = hc.alpha_over(actors, layer)                 # blur-matched authored truth (no raw weapon remnants)
    return {"layer": layer, "raw": raw, "band": band, "occluder": occluder, "truth": truth}


def _composite(sc, mode, video=None):
    video = sc["raw"] if video is None else video
    remnant = hc.weapon_remnants(video, "gold_deep", ["ember"])
    keep = hc.cd.color_mask(video, "crimson")
    ghost = hc.ghost_mask(sc["layer"][..., 3], remnant, sc["band"], mode, keep)
    base = hc.inpaint(video, ghost, exclude_sources=keep if mode == "fill_under_layer" else None)
    return hc.alpha_over(base, sc["layer"]), ghost


def _region(shape, ys, xs):
    m = np.zeros(shape, bool)
    m[ys, xs] = True
    return m


def test_v2_fill_under_layer_removes_the_double_image_by_construction():
    sc = _v2_scene()
    shape = sc["band"].shape
    blob, smear = _region(shape, slice(36, 44), slice(45, 60)), _region(shape, slice(36, 44), slice(150, 162))
    streak = sc["layer"][..., 3] == 100
    err = {}
    for mode in ("outside_core", "under_layer", "fill_under_layer"):
        comp, _ = _composite(sc, mode)
        d = np.abs(comp.astype(int) - sc["truth"].astype(int)).max(axis=-1)
        err[mode] = (int(d[blob].max()), int(d[smear].max()), int(d[streak].max()))
    # v1 (M3-A pre-registered) keeps both remnants under the streak: the double image
    assert err["outside_core"][0] > 40 and err["outside_core"][1] > 20
    # colour-based removal (M3-A post-hoc v2) catches the gold blob but not a smear no rule detects (cf. the M3-A
    # f27 residual tint)
    assert err["under_layer"][0] <= 6 and err["under_layer"][1] > 20
    # M3-B v2: nothing of the raw weapon shows through the streak, whatever its colour
    assert max(err["fill_under_layer"]) <= 6


def test_v2_keeps_occluding_actor_hand_and_unprotected_pixels():
    sc = _v2_scene()
    comp, ghost = _composite(sc, "fill_under_layer")
    occ = sc["occluder"]
    assert np.array_equal(comp[occ], sc["raw"][occ])                 # actor in front of the weapon: untouched
    assert not ghost[occ].any()
    hand = _region(occ.shape, slice(37, 43), slice(92, 98))
    assert not ghost[hand].any()                                      # generated hand shows through the streak
    assert np.array_equal(comp[hand], hc.alpha_over(sc["raw"], sc["layer"])[hand])
    far = ~hc.cd.dilate(sc["band"] | (sc["layer"][..., 3] > 0), 3)
    assert np.array_equal(comp[far], sc["raw"][far])                  # outside the band and layer: raw, bit-exact
    head = sc["layer"][..., 3] == 255
    assert (comp[head] == np.array(GOLD, np.uint8)).all()


def test_v2_dry_run_on_the_authored_truth_is_near_identity_and_stray_remnants_go():
    sc = _v2_scene()
    # dry run: the blur-matched truth as the "generated" video -> the composite reproduces it (the tool's own error)
    # (actor pixels under the streak are excluded: the truth already carries the layer there, so a dry run applies
    # it twice; in a generation the raw actor has no authored streak on it)
    dry, _ = _composite(sc, "fill_under_layer", video=sc["truth"])
    twice = hc.cd.color_mask(sc["truth"], "crimson") & (sc["layer"][..., 3] > 0)
    assert int(np.abs(dry.astype(int) - sc["truth"].astype(int)).max(axis=-1)[~twice].max()) <= 6
    # the stray gold remnant outside the layer footprint is counted before and removed after, in every mode
    a = sc["layer"][..., 3]
    assert hc.unexplained_weapon_px(sc["raw"], a, sc["band"], "gold_deep", ["ember"]) >= 48
    for mode in ("outside_core", "under_layer", "fill_under_layer"):
        comp, _ = _composite(sc, mode)
        assert hc.unexplained_weapon_px(comp, a, sc["band"], "gold_deep", ["ember"]) == 0
    with pytest.raises(ValueError, match="unknown ghost mode"):
        hc.ghost_mask(a, np.zeros_like(sc["band"]), sc["band"], "nope")
