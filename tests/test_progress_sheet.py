import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tools.admission import progress_sheet as ps

FONT = Path("C:/Windows/Fonts/arialbd.ttf")
pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None or not FONT.is_file(),
                                reason="needs ffmpeg and the Windows Arial font")


def _video(path, w, h, value):
    frames = np.full((5, h, w, 3), value, np.uint8)
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                    "-r", "24", "-i", "-", "-c:v", "libx264rgb", "-qp", "0", str(path)], input=frames.tobytes(), check=True)
    return path


def test_rows_of_different_aspect_line_up(tmp_path):
    a = _video(tmp_path / "a.mp4", 64, 40, 60)       # 1.6
    b = _video(tmp_path / "b.mp4", 96, 56, 180)      # 1.714
    out = ps.build([("old", a), ("new", b)], [0, 4], ["first", "last"], tmp_path / "sheet.png", height=56)
    probe = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_entries", "stream=width,height", "-of",
                            "csv=p=0", str(out)], capture_output=True, text=True, check=True).stdout.strip()
    assert probe == f"{2 * 96},{2 * (56 + ps.LABEL_H)}"
