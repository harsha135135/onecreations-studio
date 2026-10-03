from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_yaml_files_parse():
    files = list((ROOT / "model_registry").glob("*.yaml")) + list((ROOT / "training").rglob("*.yaml"))
    assert len(files) >= 4
    for f in files:
        assert yaml.safe_load(f.read_text(encoding="utf-8")) is not None, f


def test_registry_keeps_primary_and_experiment_roles():
    reg = yaml.safe_load((ROOT / "model_registry" / "models.yaml").read_text(encoding="utf-8"))
    roles = {m["id"]: m["role"] for m in reg["models"]}
    assert roles["ltx25_22b_distilled"] == "primary_video_candidate"
    assert roles["wan21_vace_1_3b"] == "local_small_model_experiment"


def test_powershell_scripts_are_ascii():
    # Windows PowerShell 5.1 reads BOM-less scripts as ANSI; keep them ASCII.
    scripts = sorted((ROOT / "tools" / "windows").glob("*.ps1"))
    assert {p.name for p in scripts} >= {"check_env.ps1", "oc_env.ps1"}
    for p in scripts:
        p.read_bytes().decode("ascii")


def test_m2c_prompt_has_no_camera_motion_words():
    # M2-C's camera motion must come from the control path, not text: the M2-A prompt, verbatim
    import json

    wf = {name: json.loads((ROOT / "workflows" / "ltx25" / name).read_text(encoding="utf-8"))
          for name in ("m2a_temple_api.json", "m2c_camera_api.json")}
    prompt = wf["m2c_camera_api.json"]["4"]["inputs"]["text"]
    assert prompt == wf["m2a_temple_api.json"]["4"]["inputs"]["text"]
    banned = ("camera", "orbit", "dolly", "push", "pan ", "panning", "tracking", "circl", "approach", "parallax", "zoom")
    assert not [w for w in banned if w in prompt.lower()]
