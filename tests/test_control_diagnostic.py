import numpy as np

from tools.admission import control_diagnostic as cd

H, W, N = 160, 256, 9


def scene(box_x: list[int], ball_r: list[int]) -> np.ndarray:
    """Synthetic flat-colour frames: red box moving in x, blue disc with radius ball_r."""
    frames = np.full((len(box_x), H, W, 3), 190, np.uint8)
    yy, xx = np.mgrid[0:H, 0:W]
    for i, (bx, br) in enumerate(zip(box_x, ball_r)):
        frames[i, 100:150, bx:bx + 60] = (205, 20, 20)
        if br > 0:
            frames[i][(yy - 40) ** 2 + (xx - 128) ** 2 <= br ** 2] = (20, 40, 215)
    return frames


def track(frames):
    return cd.track_colors(frames)


def test_color_masks_and_stats():
    f = scene([10], [12])[0]
    red = cd.mask_stats(cd.color_mask(f, "red"))
    blue = cd.mask_stats(cd.color_mask(f, "blue"))
    assert red["bbox"] == [10, 100, 69, 149] and red["area_px"] == 60 * 50
    assert abs(blue["cx"] - 128) < 0.5 and abs(blue["cy"] - 40) < 0.5
    assert cd.mask_stats(np.zeros((4, 4), bool)) is None
    assert cd.checkpoint_frames(49) == [0, 12, 24, 36, 48]


def test_classify_pass_partial_fail():
    gt = track(scene([10 + 20 * i for i in range(N)], [8 + 3 * i for i in range(N)]))
    same = cd.classify(gt, gt, N)
    assert same["metric_class"] == "PASS" and same["box"]["travel_frac"] == 1.0
    static_box = track(scene([10] * N, [8 + 3 * i for i in range(N)]))
    assert cd.classify(static_box, gt, N)["metric_class"] == "PARTIAL"
    reversed_all = track(scene([170 - 20 * i for i in range(N)], [32 - 3 * i for i in range(N)]))
    r = cd.classify(reversed_all, gt, N)
    assert r["metric_class"] == "FAIL" and r["box"]["direction_correct"] is False
    no_ball = track(scene([10 + 20 * i for i in range(N)], [0] * N))
    assert cd.classify(no_ball, gt, N)["metric_class"] is None
