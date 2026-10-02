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


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_encode_video_roundtrip(tmp_path):
    frames = np.tile(np.linspace(0, 255, 64, dtype=np.uint8), (5, 32, 1))
    out = tmp_path / "depth.mp4"
    make_controls.encode_video(frames, out, "24")
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                            "stream=width,height,nb_read_frames", "-of", "csv=p=0", str(out)],
                           capture_output=True, text=True, check=True).stdout.strip()
    assert probe == "64,32,5"
