import shutil
import subprocess

import numpy as np
import pytest

from tools.admission import make_controls


def test_near_is_bright_background_black_and_range_recorded():
    depth = np.full((2, 4, 6), np.inf, dtype=np.float32)
    depth[:, :, :3] = 2.0   # near
    depth[:, :2, 3:] = 8.0  # far; bottom-right stays background
    frames, meta = make_controls.depth_to_control(depth, lo_pct=0, hi_pct=100)
    assert frames.dtype == np.uint8 and frames.shape == (2, 4, 6)
    assert frames[0, 0, 0] == 255 and frames[0, 0, 5] == 0 and frames[0, 3, 5] == 0
    assert meta["near_m"] == pytest.approx(2.0) and meta["far_m"] == pytest.approx(8.0)
    assert meta["background_fraction"] == pytest.approx(6 / 24)
    with pytest.raises(ValueError):
        make_controls.depth_to_control(np.full((1, 2, 2), np.inf))


def test_default_is_official_per_clip_min_max():
    # one near outlier pixel: percentile clipping would saturate a band of pixels; min-max must not
    depth = np.linspace(2.0, 10.0, 2 * 10 * 10).reshape(2, 10, 10)
    depth[1, 0, 0] = 0.5
    frames, meta = make_controls.depth_to_control(depth)
    inv = 1.0 / depth
    expected = np.round((inv - inv.min()) / (inv.max() - inv.min()) * 255).astype(np.uint8)
    assert np.array_equal(frames, expected)
    assert (frames == 255).sum() == 1 and meta["lo_pct"] == 0 and meta["hi_pct"] == 100
    assert "min-max" in meta["convention"]
    # normalisation is global over the clip, not per frame: frame 0 alone does not reach 255
    assert frames[0].max() < 255


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_encode_video_is_lossless(tmp_path):
    rng = np.random.default_rng(0)
    frames = rng.integers(0, 256, size=(9, 32, 64), dtype=np.uint8)
    frames[:, :, :8] = np.arange(0, 256, 32, dtype=np.uint8)  # include the extremes and a ramp
    out = tmp_path / "depth.mp4"
    make_controls.encode_video(frames, out, "24")
    decoded = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             capture_output=True, check=True).stdout
    back = np.frombuffer(decoded, np.uint8).reshape(frames.shape)
    assert np.array_equal(back, frames)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=pix_fmt,width,height,nb_frames", "-of", "csv=p=0", str(out)],
                           capture_output=True, text=True, check=True).stdout.strip()
    assert probe == "64,32,yuvj420p,9"
