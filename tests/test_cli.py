import json
import shutil

import numpy as np

from onecreations.__main__ import main
from onecreations.camera import io_colmap
from onecreations.geometry import conventions

EX = "examples/diagnostic"


def test_validate_shot_ok():
    assert main(["validate-shot", EX]) == 0
    assert main(["validate-shot", EX, "--shot", "temple_parry_004"]) == 0


def test_validate_shot_json_report(capsys):
    main(["validate-shot", EX, "--json"])
    report = json.loads(capsys.readouterr().out)
    events = report["shots"]["temple_parry_004"]["events"]
    assert [e["frame_position"] for e in events] == ["54", "909/7"]


def test_validate_shot_fails_on_errors(tmp_path):
    dst = tmp_path / "p"
    shutil.copytree(EX, dst)
    shot_path = dst / "shots" / "temple_parry_004.json"
    shot = json.loads(shot_path.read_text())
    shot["generation"]["controls"] = ["depth", "pose"]
    shot_path.write_text(json.dumps(shot))
    assert main(["validate-shot", str(dst)]) == 1


def test_schemas_check():
    assert main(["schemas", "check"]) == 0


def test_camera_stats_colmap_and_retarget(tmp_path, capsys):
    assert main(["camera", "stats", f"{EX}/camera/temple_dive_to_parry_v1.csv"]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["stats"]["samples"] == 58

    eyes = [(np.cos(a) * 3, np.sin(a) * 3, 1.0) for a in np.linspace(0, 1, 5)]
    c2w = np.stack([conventions.look_at(e, (0, 0, 1)) for e in eyes])
    io_colmap.write_images_txt(tmp_path / "images.txt", c2w, [f"f{i}.png" for i in range(5)])
    assert main(["camera", "import-colmap", str(tmp_path / "images.txt"), "--fps", "24",
                 "--out", str(tmp_path / "c.npz")]) == 0

    (tmp_path / "proxies.json").write_text(json.dumps([{"type": "sphere", "id": "statue", "center": [3, 0, 1],
                                                        "radius": 0.5}]))
    rc = main(["camera", "retarget", str(tmp_path / "c.npz"), "--src", "0,0,1", "--dst", "0,0,1", "--out",
               str(tmp_path / "r.npz"), "--proxies", str(tmp_path / "proxies.json"), "--clearance", "0.15"])
    assert rc == 2  # the first pose sits inside the statue proxy
