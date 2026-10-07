"""D2 pipeline executor with the expensive stages mocked: ordering, fail-stop, resume/caching, regenerate rules,
LTX command from the CompiledShot, CONTACT-driven effect frames, grade selection, QC decisions, delivery report."""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from onecreations.director import pipeline as pl
from onecreations.director import video_qc
from onecreations.director.compiler import compile_shot
from onecreations.director.interpreter import interpret
from onecreations.director.planner import plan_to_spec
from onecreations.director.registry import load_registry

PROMPT = ("Create a cinematic shot of a horned Asura attacking an ascetic defender with a heavy mace in an ancient "
          "ruined temple at dusk. The defender guards with a trident. Use a low orbit and push-in. Add dust, debris, "
          "sparks and floor cracks on impact.")
DETERMINISTIC = ["PLAN", "VALIDATE", "COMPILE"]


@pytest.fixture(scope="module")
def reg():
    return load_registry()


def fakes(calls: list, fail: dict | None = None):
    """Fake implementations for every stage after COMPILE: each writes one small output file."""
    fail = fail or {}

    def make(sid):
        def fn(ctx):
            calls.append(sid)
            if sid in fail:
                exc = fail[sid]
                if callable(exc) and not isinstance(exc, Exception):
                    exc = exc()
                if exc is not None:
                    raise exc
            out = ctx.path(sid.lower(), "out.bin")
            out.write_bytes(f"{sid}:{ctx.attempt.get('LTX_GENERATE', 1)}".encode())
            names = {"BLENDER_BUILD": "shot_spec", "CONTROL_RENDER": "depth_control", "FIRST_FRAME": "first_frame",
                     "LTX_GENERATE": "raw", "REPAIR": "repaired", "COMPOSITE": "composite", "GRADE": "final_master",
                     "DELIVER": "final"}
            outputs = {names.get(sid, "report"): out}
            if sid == "GRADE":
                outputs["final_view"] = out
            info = {"passed": True} if sid == "FINAL_QC" else {}
            return {"outputs": outputs, "info": info}
        return fn

    return {sid: make(sid) for sid in pl.STAGES if sid not in DETERMINISTIC}


def test_full_stage_order_and_delivery_report(tmp_path, reg):
    calls = []
    rec = pl.execute(tmp_path / "r1", PROMPT, implementations=fakes(calls), registry=reg)
    assert rec["status"] == "succeeded"
    assert [s["id"] for s in rec["stages"]] == pl.STAGES
    assert calls == pl.STAGES[3:]
    assert all(s["status"] == "done" and s["key"] and "duration_s" in s for s in rec["stages"])
    for name in ("request.json", "director_plan.json", "shot_spec.json", "compiled_shot.json", "execution.json"):
        assert (tmp_path / "r1" / name).is_file()
    report = json.loads((tmp_path / "r1" / "deliverables" / "report.json").read_text())
    assert report["status"] == "succeeded" and report["request"] == PROMPT
    assert report["assets"]["vfx"] == ["impact_dust_v1", "debris_v1", "sparks_v1", "floor_cracks_v1"]
    assert report["deliverables"]["final"].endswith("final.mp4")
    assert "## Director decisions" in (tmp_path / "r1" / "deliverables" / "report.md").read_text()


def test_failed_stage_stops_downstream_and_nothing_is_delivered(tmp_path, reg):
    calls = []
    rec = pl.execute(tmp_path / "r2", PROMPT, registry=reg,
                     implementations=fakes(calls, {"PREFLIGHT_QC": pl.StageError("preflight QC failed: camera")}))
    assert rec["status"] == "failed" and rec["failed_stage"] == "PREFLIGHT_QC"
    assert "LTX_GENERATE" not in calls
    st = {s["id"]: s["status"] for s in rec["stages"]}
    assert st["PREFLIGHT_QC"] == "failed" and st["LTX_GENERATE"] == "not_run" and st["DELIVER"] == "not_run"
    report = json.loads((tmp_path / "r2" / "deliverables" / "report.json").read_text())
    assert report["deliverables"] is None and not (tmp_path / "r2" / "deliverables" / "final.mp4").exists()


def test_unsupported_prompt_fails_before_blender(tmp_path, reg):
    calls = []
    rec = pl.execute(tmp_path / "r3", "A dragon flying over Tokyo at night", implementations=fakes(calls),
                     registry=reg)
    assert rec["status"] == "failed" and rec["failed_stage"] == "PLAN" and calls == []
    assert "unsupported request" in rec["failure"]


def test_resume_skips_unchanged_stages_and_reruns_only_invalidated_ones(tmp_path, reg):
    calls = []
    run = tmp_path / "r4"
    pl.execute(run, PROMPT, implementations=fakes(calls), registry=reg)
    calls.clear()
    rec = pl.execute(run, implementations=fakes(calls), registry=reg)            # resume: everything cached
    assert calls == [] and rec["status"] == "succeeded"
    assert {s["status"] for s in rec["stages"] if s["id"] not in DETERMINISTIC} == {"cached"}
    (run / "grade" / "out.bin").unlink()                                        # a late artifact disappears
    calls.clear()
    pl.execute(run, implementations=fakes(calls), registry=reg)
    assert calls == ["GRADE"]               # regenerated byte-identical: downstream keys unchanged, no Blender/LTX
    impl = fakes(calls)
    base_grade = impl["GRADE"]

    def different_grade(ctx):                                                   # a changed grade output ...
        res = base_grade(ctx)
        Path(res["outputs"]["final_master"]).write_bytes(b"new grade")
        return res

    impl["GRADE"] = different_grade
    (run / "grade" / "out.bin").unlink()
    calls.clear()
    pl.execute(run, implementations=impl, registry=reg)
    assert calls == ["GRADE", "FINAL_QC", "DELIVER"]                            # ... invalidates only its dependants
    calls.clear()
    pl.execute(run, implementations=fakes(calls), registry=reg, from_stage="COMPOSITE")
    assert calls == ["COMPOSITE", "GRADE", "FINAL_QC", "DELIVER"]
    with pytest.raises(ValueError, match="immutable"):
        pl.execute(run, "a different prompt", implementations=fakes([]), registry=reg)


def test_regenerate_only_by_preregistered_rule_and_once(tmp_path, reg):
    calls = []
    state = {"n": 0}

    def post_qc():
        state["n"] += 1
        return pl.RegenerateRequested(["video_valid"]) if state["n"] == 1 else None

    rec = pl.execute(tmp_path / "r5", PROMPT, registry=reg, implementations=fakes(calls, {"POST_GENERATION_QC": post_qc}))
    assert rec["status"] == "succeeded" and calls.count("LTX_GENERATE") == 2
    assert [s["status"] for s in rec["stages"] if s["id"] == "POST_GENERATION_QC"] == ["superseded", "done"]
    calls.clear()
    rec = pl.execute(tmp_path / "r6", PROMPT, registry=reg,
                     implementations=fakes(calls, {"POST_GENERATION_QC": lambda: pl.RegenerateRequested(["x"])}))
    assert rec["status"] == "failed" and calls.count("LTX_GENERATE") == 2        # at most one regeneration


def test_ltx_technical_failure_retries_once_then_fails(tmp_path, reg):
    calls = []
    rec = pl.execute(tmp_path / "r7", PROMPT, registry=reg,
                     implementations=fakes(calls, {"LTX_GENERATE": pl.StageError("LTX attempt failed (exit 1)")}))
    assert rec["status"] == "failed" and calls.count("LTX_GENERATE") == 2 and "POST_GENERATION_QC" not in calls


def _compiled(reg, prompt=PROMPT):
    return compile_shot(plan_to_spec(interpret(prompt, reg), reg, "t"), reg)


def test_ltx_guard_and_command_from_compiled_shot(tmp_path, reg, monkeypatch):
    ctx = pl.Ctx(run_dir=tmp_path / "r8", request=PROMPT, options=pl.Options(), registry=reg)
    ctx.compiled = _compiled(reg)
    monkeypatch.setattr(pl, "free_ram_gb", lambda: 4.0)
    with pytest.raises(pl.StageError, match="pre-registered guard"):
        pl.st_ltx(ctx)
    for sid, name in (("FIRST_FRAME", "first_frame"), ("CONTROL_RENDER", "depth_control")):
        p = ctx.path("controls", f"{name}.bin")
        p.write_bytes(name.encode())
        ctx.outputs[sid] = {name: str(p)}
    wf = ctx.path("generation", "workflow_api.json")
    wf.write_text("{}")
    cmd = pl.ltx_command(ctx, wf, tmp_path / "r8" / "generation", "lbl")
    assert "comfy_run.py" in " ".join(cmd) and str(tmp_path / "r8" / "controls") in cmd
    assert "seed=1000" in cmd and "steps=8" in cmd and "resolution=768x448" in cmd and "frames=49" in cmd
    from onecreations.director.compiler import compiled_workflow
    w = compiled_workflow(ctx.compiled)
    assert w["8"]["inputs"]["noise_seed"] == 1000 and (w["7"]["inputs"]["width"], w["7"]["inputs"]["height"]) == (768, 448)


def test_contact_drives_effect_frames_and_grade_shake(reg):
    c = _compiled(reg)
    ctx = pl.Ctx(run_dir=Path("."), request=PROMPT, options=pl.Options(), registry=reg, compiled=c)
    fx = next(ly for ly in c.layers.layers if ly.id == "impact_fx")
    assert pl._effect_frames(ctx, fx) == "30-49"                                  # Blender frames = CONTACT 29 + 1
    slow = _compiled(reg, PROMPT.replace("attacking", "slowly attacking"))
    ctx.compiled = slow
    assert pl._effect_frames(ctx, next(ly for ly in slow.layers.layers if ly.id == "impact_fx")) == "33-49"
    assert c.grade["shake"] == [] and not any(ly.id == "impact_flash" for ly in c.layers.layers)


def test_grade_stage_uses_the_compiled_grade(tmp_path, reg):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg")
    from onecreations.director import media
    ctx = pl.Ctx(run_dir=tmp_path / "r9", request=PROMPT, options=pl.Options(), registry=reg, compiled=_compiled(reg))
    comp = ctx.path("composite", "composite.mp4")
    media.encode_rgb(np.full((49, 32, 48, 3), 100, np.uint8), comp)
    ctx.outputs["COMPOSITE"] = {"composite": str(comp)}
    res = pl.st_grade(ctx)
    meta = json.loads((tmp_path / "r9" / "grade" / "final.json").read_text())
    assert meta["params"]["contrast"] == ctx.compiled.grade["contrast"] and meta["params"]["shake"] == []
    assert Path(res["outputs"]["final_master"]).is_file() and media.probe(res["outputs"]["final_master"])["frames"] == 49


def test_qc_decisions_are_data(reg):
    c = _compiled(reg)
    ok = {"passed": True, "on_fail": "fail"}
    weapon = {"passed": False, "on_fail": "repair"}
    assert video_qc.decide(c, {"a": ok, "weapon_integrity": weapon})["status"] == "proceed"
    d = video_qc.decide(c, {"weapon_integrity": weapon})
    assert d["repairs"][0]["object"] == "MACE" and d["repairs"][0]["qc_evidence"] == ["weapon_integrity"]
    assert video_qc.decide(c, {"contact_timing": {"passed": False, "on_fail": "fail"}})["status"] == "fail"
    assert video_qc.decide(c, {"video_valid": {"passed": False, "on_fail": "regenerate"}})["status"] == "regenerate"
    unprotected = c.model_copy(deep=True)
    for o in unprotected.semantic_objects:
        o.policy.geometry = "generative"
    assert video_qc.decide(unprotected, {"weapon_integrity": weapon})["status"] == "fail"


PARRY = ("Create a cinematic shot of a horned Asura attacking an ascetic defender with a heavy mace in an ancient "
         "ruined temple at dusk. The defender parries the blow with a trident. Use a low orbit and push-in.")


def test_parry_qc_is_declared_only_for_contact_shots(reg):
    d2 = {q.id for q in _compiled(reg).qc}
    parry = _compiled(reg, PARRY)
    ids = {q.id for q in parry.qc}
    new = {"defender_stationary_root", "defender_weapon_axis", "contact_geometry", "contact_visible",
           "defender_weapon_visible", "defender_framing", "trident_integrity"}
    assert not (d2 & new) and ids == d2 | new
    q = {c.id: c for c in parry.qc}
    assert q["defender_framing"].params["frames"] == [0, 12, 24, 29, 36, 48]
    assert q["trident_integrity"].params["on_fail"] == "repair" and q["defender_framing"].params["on_fail"] == "fail"
    assert q["weapon_bone_projection"].params["min_visible_frac"] == 0.9
    assert "min_visible_frac" not in {c.id: c for c in _compiled(reg).qc}["weapon_bone_projection"].params


def test_parry_repair_evidence_goes_to_the_named_weapon(reg):
    c = _compiled(reg, PARRY)
    d = video_qc.decide(c, {"trident_integrity": {"passed": False, "on_fail": "repair", "object": "sc_trident"},
                            "weapon_integrity": {"passed": False, "on_fail": "repair", "object": "sc_mace_head"}})
    ev = {r["object"]: r.get("qc_evidence", []) for r in d["repairs"]}
    assert d["status"] == "proceed" and ev == {"MACE": ["weapon_integrity"], "TRIDENT": ["trident_integrity"]}
    legacy = video_qc.decide(c, {"weapon_integrity": {"passed": False, "on_fail": "repair"}})  # D2 record: no object
    assert all(r["qc_evidence"] == ["weapon_integrity"] for r in legacy["repairs"])
    unknown = video_qc.decide(c, {"x": {"passed": False, "on_fail": "repair", "object": "sc_nothing"}})
    assert unknown["status"] == "fail"


def test_thin_weapon_check_uses_only_the_weapon_pixels(reg):
    c = _compiled(reg, PARRY)
    rng = np.random.default_rng(0)
    n, h, w = 49, 40, 60
    idx = np.zeros((n, h, w), np.uint8)
    idx[:, 18:21, 5:55] = 10                                     # a long thin "trident" across the frame
    ref = rng.integers(0, 255, (n, h, w)).astype(np.float32)
    good = ref + rng.normal(0, 4, ref.shape)                     # weapon (and everything else) held
    bad = good.copy()
    bad[30][17:22, :] = rng.integers(0, 255, (5, w))             # frame 30: only the weapon's pixels break
    p = {"from_event": "parry.GUARD_END", "dilate_px": 1, "min_ncc": 0.4}
    assert video_qc.check_thin_weapon(c, ref, good, idx, 10, p)["passed"]
    r = video_qc.check_thin_weapon(c, ref, bad, idx, 10, p)
    assert r["failed_frames"] == [30] and r["per_frame_ncc"]["29"] > 0.9 and "7" not in r["per_frame_ncc"]


def test_contact_timing_without_onset_fails_instead_of_crashing(reg):
    """d3_run1: the raw weapon head never came within max_offset_px of its contact position; the check must report a
    failure (observed_onset None), not raise."""
    c = _compiled(reg)
    rng = np.random.default_rng(1)
    n, h, w = 49, 120, 160
    idx = np.zeros((n, h, w), np.uint8)
    idx[:, 50:70, 70:90] = 8
    ref = rng.integers(0, 255, (n, h, w)).astype(np.float32)
    raw = rng.integers(0, 255, (n, h, w)).astype(np.float32)          # nothing like the reference anywhere
    p = {"search_frames": 4, "radius_px": 24, "onset_frac": 0.9, "tol_frames": 2, "max_offset_px": 0, "min_ncc": 0.45}
    r = video_qc.check_contact_timing(c, ref, raw, idx, 8, p)
    assert r["passed"] is False and r["observed_onset"] is None and r["offset_frames"] is None


def test_undeclared_evaluator_fails_loudly(reg):
    c = _compiled(reg).model_copy(deep=True)
    c.qc = [c.qc[-1].model_copy(update={"id": "made_up", "stage": "post_generation"})]
    v = np.zeros((49, 448, 768, 3), np.uint8)
    idx = np.zeros((49, 448, 768), np.uint8)
    with pytest.raises(ValueError, match="made_up"):
        video_qc.post_generation(c, v, v, idx, {"sc_asura": 1, "sc_mace_head": 8})


def test_video_validity_and_holes():
    good = np.random.default_rng(0).integers(0, 255, (5, 20, 30, 3), dtype=np.uint8)
    p = {"min_std": 3.0, "spike_abs": 300.0, "spike_rel": 1e9}
    assert video_qc.check_video_valid(good, 5, (30, 20), p)["passed"]
    bad = good.copy()
    bad[2] = 128
    r = video_qc.check_video_valid(bad, 5, (30, 20), p)
    assert not r["passed"] and r["blank_frames"] == [2]
    assert not video_qc.check_video_valid(good, 6, (30, 20), p)["passed"]
    holes = good.copy()
    holes[1, :10] = 0
    assert video_qc.check_output_integrity(good, holes, {"max_hole_frac": 0.005})["hole_frames"] == [1]


def test_preflight_still_stops_before_ltx(tmp_path, reg, monkeypatch):
    from onecreations import blender_bridge as bb
    from onecreations.director import executor, qc
    seen = []
    monkeypatch.setattr(bb, "run_script", lambda script, args, **kw: seen.append(script))
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append(" ".join(map(str, cmd))))
    monkeypatch.setattr(shutil, "copyfile", lambda a, b: None)
    monkeypatch.setattr(executor, "write_masks", lambda *a, **k: {})
    monkeypatch.setattr(qc, "evaluate_preflight", lambda *a, **k: {"passed": True, "checks": {}, "not_run": []})
    (tmp_path / "shot_spec.json").write_text("{}")
    executor.preflight(_compiled(reg), tmp_path)
    assert "build_showcase_scene.py" in seen and not any("comfy_run" in s or "monitor.py" in s for s in seen)
