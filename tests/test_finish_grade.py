import json
import shutil
import subprocess

import numpy as np
import pytest

from tools.admission import control_diagnostic as cd
from tools.admission import finish_grade as fg

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


def test_shake_offsets_and_edge_clamp():
    frames = np.zeros((3, 4, 6, 3), np.uint8)
    frames[:, :, :, 0] = np.arange(6, dtype=np.uint8)[None, None, :] * 10
    out = fg.shake(frames, [[1, 2, 0], [9, 1, 1]])            # frame 9 is outside the clip: ignored
    assert np.array_equal(out[0], frames[0]) and np.array_equal(out[2], frames[2])
    assert out[1, 0, :, 0].tolist() == [0, 0, 0, 10, 20, 30]  # shifted right by 2, left edge clamped


def test_filter_chain_and_run(tmp_path):
    chain = fg.filter_chain(dict(fg.DEFAULT, vignette_angle=0, grain=0))
    assert chain.startswith("eq=contrast=1.05") and "vignette" not in chain and "noise" not in chain
    frames = np.full((4, 32, 48, 3), 120, np.uint8)
    src = tmp_path / "in.mp4"
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "48x32",
                    "-r", "24", "-i", "-", "-c:v", "libx264rgb", "-qp", "0", str(src)], input=frames.tobytes(), check=True)
    meta = fg.run(src, tmp_path / "out", {"shake": [[1, 1, 0]]})
    assert meta["frames"] == 4 and meta["size"] == [48, 32] and "noise=" in meta["filter_chain"]
    assert cd.decode_rgb(tmp_path / "out" / "final_master.mp4").shape == (4, 32, 48, 3)
    assert json.loads((tmp_path / "out" / "final.json").read_text())["params"]["shake"] == [[1, 1, 0]]
