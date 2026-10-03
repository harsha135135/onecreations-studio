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


def test_m3b_workflow_is_m3a_with_only_the_output_prefix_changed():
    # M3-B changes only the first frame / control inputs: the graph, prompt, seed, steps and strengths are M3-A's
    import json

    a, b = (json.loads((ROOT / "workflows" / "ltx25" / n).read_text(encoding="utf-8"))
            for n in ("m3a_action_api.json", "m3b_character_api.json"))
    assert a.keys() == b.keys()
    changed = [k for k in a if a[k]["class_type"] != b[k]["class_type"] or a[k]["inputs"] != b[k]["inputs"]]
    assert changed == ["15"]
    assert b["15"]["inputs"] == dict(a["15"]["inputs"], filename_prefix="ltx25_m3b/ltx25_m3b")


def test_m3b_preregistration_is_complete_and_loadable():
    import json

    from tools.admission import silhouette_compare

    path = ROOT / "admission_records" / "2026-10-03_ltx25-m3b-character_preregistration.json"
    pre = json.loads(path.read_text(encoding="utf-8"))
    assert pre["registered_before_generation"] is True
    gate = silhouette_compare.load_gate(path)
    assert {"m3a_asura", "m3a_defender", "m3a_mace_head", "m3a_mace_shaft"} <= set(gate["objects"])
    assert all({"min_iou", "max_centroid_px", "area_ratio"} <= set(v) for v in gate["objects"].values())
    assert "fill_under_layer" in pre["hybrid_v2"]["manifest"]
    assert {"control_pass", "appearance_pass", "full_pass"} <= set(pre["classification"])
    assert "seed" in pre["generation_budget_and_retry"]["never_a_retry"]
