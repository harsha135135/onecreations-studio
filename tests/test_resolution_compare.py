import pytest

from tools.admission import resolution_compare as rc


def test_guide_grid_matches_the_pinned_union_graph():
    assert rc.guide_grid(512, 320) == {"output_px": [512, 320], "latent": [16, 10], "guide_resize_px": [256, 160],
                                       "guide_cells": [8, 5], "output_px_per_guide_cell": 64}
    g = rc.guide_grid(768, 448)
    assert g["latent"] == [24, 14] and g["guide_resize_px"] == [384, 224] and g["guide_cells"] == [12, 7]
    assert g["output_px_per_guide_cell"] == 64
    with pytest.raises(ValueError):
        rc.guide_grid(500, 320)                        # not a multiple of the VAE's 32 px
    with pytest.raises(ValueError):
        rc.guide_grid(544, 320)                        # latent width 17 is not divisible by the downscale factor 2


def test_motion_reports_pixels_and_cells():
    track = [{"cx": 0.0, "cy": 0.0}, {"cx": 3.0, "cy": 4.0}, None, {"cx": 3.0, "cy": 132.0}, {"cx": 3.0, "cy": 260.0}]
    m = rc.motion(track, 64)
    assert m["speed_px"] == [5.0, None, None, 128.0]
    assert m["peak_px_per_frame"] == 128.0 and m["peak_cells_per_frame"] == 2.0 and m["peak_frame"] == 3
    assert m["path_px"] == 133.0 and m["path_cells"] == round(133 / 64, 2)


def test_retention_summary_over_fast_and_worst_regions():
    ratios = [0.9] * 24 + [0.6, 0.01, 0.5, 0.7, 0.8] + [0.95] * 20
    s = rc.retention_summary(ratios, range(24, 29), range(25, 28), 0.25)
    assert s["fast_worst"] == 0.01 and s["fast_worst_frame"] == 25 and s["fast_median"] == 0.6
    assert s["worst_region_median"] == 0.5 and s["severe_frames"] == [25]
    assert s["outside_fast_median"] == pytest.approx(0.9)        # 24 x 0.9 and 20 x 0.95 outside the fast region
    assert rc.retention_summary([None] * 30, range(24, 29), range(25, 28), 0.25)["fast_worst"] is None
