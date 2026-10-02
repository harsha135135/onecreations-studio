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
