"""D2: one-command prompt -> final video for the supported shot class.

    PLAN -> VALIDATE -> COMPILE -> BLENDER_BUILD -> CONTROL_RENDER -> FIRST_FRAME -> PREFLIGHT_QC -> LTX_GENERATE
    -> POST_GENERATION_QC -> REPAIR -> VFX -> COMPOSITE -> GRADE -> FINAL_QC -> DELIVER

Every stage reads the CompiledShot (or the outputs of earlier stages) and nothing else: no hidden configuration.
Each stage gets a content key from its inputs (config sections + upstream output hashes); a resumed run skips a
stage whose key and recorded outputs are unchanged, so a late failure (grade, encode) never reruns Blender or LTX,
and a changed spec invalidates exactly the dependent stages. A failing stage stops the run; nothing downstream runs
and nothing is delivered as successful. The proven implementations are reused: the Blender builders, oc_export,
make_controls, render_reference / render_stills / render_layers, comfy_run under monitor, hybrid_composite (two
passes: protected geometry = REPAIR, effects = COMPOSITE) and finish_grade.

Run directory (data root, never Git):
    runs/<run_id>/request.json director_plan.json shot_spec.json compiled_shot.json execution.json
                  preflight/ controls/ generation/ repair/ vfx/ composite/ grade/ qc/ deliverables/
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from onecreations.blender_bridge import REPO_ROOT
from onecreations.hashing import content_hash

STAGES = ["PLAN", "VALIDATE", "COMPILE", "BLENDER_BUILD", "CONTROL_RENDER", "FIRST_FRAME", "PREFLIGHT_QC",
          "LTX_GENERATE", "POST_GENERATION_QC", "REPAIR", "VFX", "COMPOSITE", "GRADE", "FINAL_QC", "DELIVER"]
PIPELINE_VERSION = "d2.1"
DATA_ROOT = Path(os.environ.get("ONECREATIONS_DATA", r"G:\onecreations"))


class StageError(RuntimeError):
    pass


@dataclass
class Options:
    first_frame_samples: int = 1024
    reference_samples: int = 64
    layer_samples: int | None = None              # None: each layer's own render.samples
    device: str = "OPTIX"
    min_free_ram_gb: float = 20.0                 # pre-registered LTX guard (RAM is the binding resource)
    technical_retries: int = 1                    # LTX technical failure / pre-registered regenerate rule
    ltx_timeout_s: int = 3600


@dataclass
class Ctx:
    run_dir: Path
    request: str | None
    options: Options
    registry: object = None
    plan: object = None
    spec: object = None
    compiled: object = None
    outputs: dict = field(default_factory=dict)   # stage -> {name: path}
    info: dict = field(default_factory=dict)      # stage -> info dict
    attempt: dict = field(default_factory=dict)

    def path(self, *parts) -> Path:
        p = self.run_dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


def _sha(p: Path) -> str:
    from onecreations.director.media import sha256

    return sha256(p)


def _now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _out_sha(ctx: Ctx, stage: str, name: str) -> str:
    return _sha(Path(ctx.outputs[stage][name]))


# --- stage dependency keys -----------------------------------------------------------------------------------------

def stage_inputs(stage: str, ctx: Ctx) -> dict:
    """What a stage's result depends on (config sections and upstream output hashes)."""
    c = ctx.compiled
    if stage in ("PLAN", "VALIDATE", "COMPILE"):
        return {"request": ctx.request, "registry": ctx.registry.sha256 if ctx.registry else None}
    if stage == "BLENDER_BUILD":
        return {"scene_build": c.scene_build}
    if stage == "CONTROL_RENDER":
        return {"built_spec": _out_sha(ctx, "BLENDER_BUILD", "shot_spec"), "ref_samples": ctx.options.reference_samples}
    if stage == "FIRST_FRAME":
        return {"built_spec": _out_sha(ctx, "BLENDER_BUILD", "shot_spec"), "samples": ctx.options.first_frame_samples}
    if stage == "PREFLIGHT_QC":
        return {"depth": _out_sha(ctx, "CONTROL_RENDER", "depth_control"),
                "first_frame": _out_sha(ctx, "FIRST_FRAME", "first_frame"),
                "qc": [q.model_dump(mode="json") for q in c.qc if q.stage == "preflight"]}
    if stage == "LTX_GENERATE":
        return {"job": c.generation.model_dump(mode="json"), "first_frame": _out_sha(ctx, "FIRST_FRAME", "first_frame"),
                "depth": _out_sha(ctx, "CONTROL_RENDER", "depth_control")}
    if stage == "POST_GENERATION_QC":
        return {"raw": _out_sha(ctx, "LTX_GENERATE", "raw"),
                "qc": [q.model_dump(mode="json") for q in c.qc if q.stage == "post_generation"]}
    if stage == "REPAIR":
        return {"raw": _out_sha(ctx, "LTX_GENERATE", "raw"), "built_spec": _out_sha(ctx, "BLENDER_BUILD", "shot_spec"),
                "layers": [ly.model_dump(mode="json") for ly in c.layers.layers if ly.kind == "protected_geometry"]}
    if stage == "VFX":
        return {"built_spec": _out_sha(ctx, "BLENDER_BUILD", "shot_spec"),
                "layers": [ly.model_dump(mode="json") for ly in c.layers.layers if ly.kind == "effect"]}
    if stage == "COMPOSITE":
        return {"repaired": _out_sha(ctx, "REPAIR", "repaired"),
                "vfx": {k: v for k, v in ctx.info.get("VFX", {}).get("layer_hashes", {}).items()}}
    if stage == "GRADE":
        return {"composite": _out_sha(ctx, "COMPOSITE", "composite"), "grade": c.grade}
    if stage == "FINAL_QC":
        return {"final": _out_sha(ctx, "GRADE", "final_master"),
                "qc": [q.model_dump(mode="json") for q in c.qc if q.stage == "final"]}
    if stage == "DELIVER":
        return {"final": _out_sha(ctx, "GRADE", "final_view"), "final_qc": ctx.info.get("FINAL_QC", {}).get("passed")}
    raise KeyError(stage)


# --- stage implementations (proven tools) ----------------------------------------------------------------------------

def _tools():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def st_plan(ctx: Ctx) -> dict:
    from onecreations.director.interpreter import interpret
    from onecreations.director.planner import plan_to_spec

    ctx.plan = interpret(ctx.request, ctx.registry)
    ctx.path("director_plan.json").write_text(ctx.plan.model_dump_json(indent=1), encoding="utf-8")
    if not ctx.plan.supported:
        raise StageError("unsupported request: " + "; ".join(ctx.plan.unsupported or ["missing slots"]))
    ctx.spec = plan_to_spec(ctx.plan, ctx.registry, ctx.run_dir.name)
    ctx.path("shot_spec.json").write_text(ctx.spec.model_dump_json(indent=1), encoding="utf-8")
    return {"outputs": {"director_plan": ctx.run_dir / "director_plan.json", "shot_spec": ctx.run_dir / "shot_spec.json"},
            "info": {"warnings": ctx.plan.warnings}}


def st_validate(ctx: Ctx) -> dict:
    from onecreations.director.validate import validate_spec

    issues = validate_spec(ctx.spec, ctx.registry)
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise StageError("invalid ShotSpec: " + "; ".join(f"{i.code}: {i.message}" for i in errors))
    return {"outputs": {}, "info": {"issues": [i.to_dict() for i in issues]}}


def st_compile(ctx: Ctx) -> dict:
    from onecreations.director.compiler import compile_shot

    ctx.compiled = compile_shot(ctx.spec, ctx.registry)
    p = ctx.path("compiled_shot.json")
    p.write_text(ctx.compiled.model_dump_json(indent=1), encoding="utf-8")
    return {"outputs": {"compiled_shot": p}, "info": {"events": {e.name: e.frame for e in ctx.compiled.events}}}


def st_build(ctx: Ctx) -> dict:
    from onecreations import blender_bridge as bb

    cfg = ctx.path("preflight", "scene_build.json")
    cfg.write_text(json.dumps(ctx.compiled.scene_build, indent=1), encoding="utf-8")
    blend, spec = ctx.path("preflight", "scene.blend"), ctx.path("preflight", "shot_spec.json")
    bb.run_script(ctx.compiled.scene_build.get("builder", "build_showcase_scene.py"),
                  ["--out", blend, "--spec", spec, "--config", cfg], timeout=1800)
    return {"outputs": {"blend": blend, "shot_spec": spec}}


def st_controls(ctx: Ctx) -> dict:
    from onecreations import blender_bridge as bb

    pre = ctx.run_dir / "preflight"
    blend = pre / "scene.blend"
    export_args = ["--out", pre / "export", "--passes", "--probes", "--shot-id", ctx.compiled.shot_id]
    if ctx.compiled.scene_build.get("material_index_pass"):
        export_args.append("--material-index")
    bb.run_script("oc_export.py", export_args, blend=blend, timeout=3600)
    depth = ctx.path("controls", "depth_control.mp4")
    subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "admission" / "make_controls.py"), str(pre / "export"),
                    "--out", str(depth)], check=True, capture_output=True)
    s = str(ctx.options.reference_samples)
    bb.run_script("render_reference.py", ["--out-dir", pre, "--samples", s, "--device", ctx.options.device],
                  blend=blend, timeout=7200)
    bb.run_script("render_reference.py", ["--out-dir", pre, "--samples", s, "--motion-blur", "0.5",
                                          "--device", ctx.options.device], blend=blend, timeout=7200)
    return {"outputs": {"export_manifest": pre / "export" / "export_manifest.json", "depth_control": depth,
                        "depth_sidecar": depth.with_suffix(".json"), "reference": pre / "reference_preview.mp4",
                        "reference_blur": pre / "reference_motionblur.mp4"}}


def st_first_frame(ctx: Ctx) -> dict:
    from onecreations import blender_bridge as bb

    tmp = ctx.run_dir / "preflight" / "first_frame_render"
    bb.run_script("render_stills.py", ["--out-dir", tmp, "--frames", "1", "--samples",
                                       str(ctx.options.first_frame_samples), "--device", ctx.options.device],
                  blend=ctx.run_dir / "preflight" / "scene.blend", timeout=3600)
    ff = ctx.path("controls", "first_frame.png")
    shutil.copyfile(tmp / "still_0001.png", ff)
    return {"outputs": {"first_frame": ff}, "info": {"samples": ctx.options.first_frame_samples}}


def st_preflight_qc(ctx: Ctx) -> dict:
    from onecreations.director.executor import write_masks
    from onecreations.director.qc import evaluate_preflight

    pre = ctx.run_dir / "preflight"
    built = json.loads((pre / "shot_spec.json").read_text(encoding="utf-8"))
    masks = write_masks(ctx.compiled, pre / "export", ctx.run_dir / "preflight" / "masks")
    rep = evaluate_preflight(ctx.compiled, pre / "export", ctx.run_dir / "controls" / "first_frame.png", built)
    p = ctx.path("qc", "preflight.json")
    p.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    if not rep["passed"]:
        raise StageError("preflight QC failed: " + ", ".join(k for k, v in rep["checks"].items() if not v["passed"]))
    return {"outputs": {"report": p}, "info": {"passed": True, "masks": sorted(masks)}}


def _comfy_env() -> dict:
    d = DATA_ROOT
    env = dict(os.environ, ONECREATIONS_DATA=str(d), HF_HOME=str(d / "hf-cache"), HF_HUB_DISABLE_TELEMETRY="1",
               TORCH_HOME=str(d / "hf-cache" / "torch"), UV_CACHE_DIR=str(d / "temp" / "uv-cache"),
               PIP_CACHE_DIR=str(d / "temp" / "pip-cache"), TEMP=str(d / "temp" / "tmp"), TMP=str(d / "temp" / "tmp"))
    for k in ("HF_HOME", "TORCH_HOME", "UV_CACHE_DIR", "PIP_CACHE_DIR", "TEMP"):
        Path(env[k]).mkdir(parents=True, exist_ok=True)
    return env


def free_ram_gb() -> float:
    import psutil

    return psutil.virtual_memory().available / 1024 ** 3


def ltx_command(ctx: Ctx, workflow: Path, gen: Path, label: str) -> list[str]:
    d = DATA_ROOT
    comfy = [str(d / "comfy" / ".venv" / "Scripts" / "python.exe"), str(d / "comfy" / "ComfyUI" / "main.py"),
             "--port", "8188", "--disable-auto-launch", "--extra-model-paths-config",
             str(d / "comfy" / "extra_model_paths.yaml"), "--output-directory", str(gen / "out"),
             "--input-directory", str(ctx.run_dir / "controls"), "--temp-directory", str(d / "temp" / "comfy")]
    job = ctx.compiled.generation
    meta = [f"run={ctx.run_dir.name}", f"workflow_sha256={_sha(workflow)}", f"seed={job.seed}", f"steps={job.steps}",
            f"resolution={job.resolution[0]}x{job.resolution[1]}", f"frames={job.frames}",
            f"first_frame_sha256={_out_sha(ctx, 'FIRST_FRAME', 'first_frame')}",
            f"depth_control_sha256={_out_sha(ctx, 'CONTROL_RENDER', 'depth_control')}"]
    tools = REPO_ROOT / "tools" / "admission"
    return [sys.executable, str(tools / "monitor.py"), "--label", label, "--interval", "1", "--out-dir", str(gen),
            "--meta", *meta, "--notes", f"D2 pipeline run {ctx.run_dir.name} (unattended)", "--",
            sys.executable, str(tools / "comfy_run.py"), "--workflow", str(workflow), "--repeat", "1",
            "--timeout", str(ctx.options.ltx_timeout_s), "--ready-timeout", "900", "--report", str(gen / "report.json"),
            "--launch-log", str(gen / "comfy.log"), "--", *comfy]


def st_ltx(ctx: Ctx) -> dict:
    from onecreations.director.compiler import compiled_workflow

    free = free_ram_gb()
    if free < ctx.options.min_free_ram_gb:
        raise StageError(f"only {free:.1f} GB RAM free (< {ctx.options.min_free_ram_gb} GB pre-registered guard): "
                         f"close browsers and resume")
    gen = ctx.run_dir / "generation"
    attempt = ctx.attempt.get("LTX_GENERATE", 1)
    wf = compiled_workflow(ctx.compiled)
    out_node = next(k for k, v in wf.items() if v.get("class_type") == "SaveVideo")
    wf[out_node]["inputs"]["filename_prefix"] = f"attempt{attempt}/raw"
    wpath = ctx.path("generation", "workflow_api.json")
    wpath.write_text(json.dumps(wf, indent=2), encoding="utf-8")
    t0 = time.perf_counter()
    proc = subprocess.run(ltx_command(ctx, wpath, gen, f"{ctx.run_dir.name}-ltx-a{attempt}"), env=_comfy_env(),
                          capture_output=True, text=True, cwd=str(REPO_ROOT))
    (gen / f"attempt{attempt}.log").write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")
    vids = sorted((gen / "out" / f"attempt{attempt}").glob("*.mp4"))
    if proc.returncode != 0 or not vids:
        raise StageError(f"LTX attempt {attempt} failed (exit {proc.returncode}, {len(vids)} outputs)")
    raw = ctx.path("generation", "raw.mp4")
    shutil.copyfile(vids[-1], raw)
    summary = json.loads((gen / "records.jsonl").read_text(encoding="utf-8").splitlines()[-1])["summary"]
    rep = json.loads((gen / "report.json").read_text(encoding="utf-8"))
    job = rep["jobs"][0]
    return {"outputs": {"raw": raw, "workflow": wpath}, "info": {
        "attempt": attempt, "wall_s": round(time.perf_counter() - t0, 1), "comfy_wall_s": job.get("wall_s"),
        "phases_s": job.get("phases_s"), "denoise_steps": job.get("denoise_steps"), "startup_s": rep.get("startup_s"),
        "telemetry": summary, "free_ram_gb_before": round(free, 2), "backend": ctx.compiled.generation.backend,
        "seed": ctx.compiled.generation.seed, "steps": ctx.compiled.generation.steps,
        "resolution": list(ctx.compiled.generation.resolution), "frames": ctx.compiled.generation.frames}}


def _load_video_inputs(ctx: Ctx):
    from onecreations.blender_bundle import load_bundle
    from onecreations.director import media

    b = load_bundle(ctx.run_dir / "preflight" / "export")
    return b, media.decode_rgb(ctx.run_dir / "preflight" / "reference_preview.mp4")


def st_post_qc(ctx: Ctx) -> dict:
    from onecreations.director import media, video_qc

    b, ref = _load_video_inputs(ctx)
    raw = media.decode_rgb(Path(ctx.outputs["LTX_GENERATE"]["raw"]))
    res = video_qc.post_generation(ctx.compiled, ref, raw, b.passes()["object_index"],
                                   b.manifest.passes.object_index_map)
    decision = video_qc.decide(ctx.compiled, res)
    p = ctx.path("qc", "post_generation.json")
    p.write_text(json.dumps({"checks": res, "decision": decision}, indent=1), encoding="utf-8")
    if decision["status"] == "fail":
        raise StageError("post-generation QC: non-repairable failure in " + ", ".join(decision["fail_for"]))
    if decision["status"] == "regenerate":
        raise RegenerateRequested(decision["regenerate_for"])
    return {"outputs": {"report": p}, "info": {"decision": decision,
                                               "passed": {k: v["passed"] for k, v in res.items()}}}


class RegenerateRequested(StageError):
    pass


def _layer_render(ctx: Ctx, layer, out_dir: Path, frames: str | None) -> None:
    from onecreations import blender_bridge as bb

    args = ["--spec", ctx.run_dir / "preflight" / "shot_spec.json", "--layer", layer.id, "--out-dir", out_dir,
            "--device", ctx.options.device]
    if frames:
        args += ["--frames", frames]
    bb.run_script("render_layers.py", args, blend=ctx.run_dir / "preflight" / "scene.blend", timeout=7200)


def _effect_frames(ctx: Ctx, layer) -> str:
    from fractions import Fraction

    _tools()
    from tools.admission import hybrid_composite as hc

    start = hc.trigger_frame(ctx.compiled.action_timeline.model_dump(mode="json"), layer.trigger.phase,
                             layer.trigger.edge, Fraction(ctx.compiled.fps))
    end = min(ctx.compiled.frames, start + layer.duration_frames) - 1
    return f"{start + 1}-{end + 1}"                      # Blender frames


def st_repair(ctx: Ctx) -> dict:
    _tools()
    from tools.admission import hybrid_composite as hc

    protected = [ly for ly in ctx.compiled.layers.layers if ly.kind == "protected_geometry"]
    out = ctx.path("repair", "repaired.mp4")
    if not protected:
        shutil.copyfile(ctx.outputs["LTX_GENERATE"]["raw"], out)
        return {"outputs": {"repaired": out}, "info": {"note": "no protected objects: raw passed through"}}
    dirs = {}
    for ly in protected:
        dirs[ly.id] = ctx.run_dir / "repair" / "layers" / ly.id
        _layer_render(ctx, ly, dirs[ly.id], None)
    res = hc.run(ctx.run_dir / "preflight", Path(ctx.outputs["LTX_GENERATE"]["raw"]), ctx.run_dir / "repair",
                 kinds=("protected_geometry",), layer_dirs=dirs, output_name="repaired.mp4")
    rep = res["report"]["layers"]
    return {"outputs": {"repaired": out, "report": ctx.run_dir / "repair" / "composite_report.json"},
            "info": {"layers": {k: {"protected_frames": len(v["protected_frames"]), "ghost_mode": v["ghost_mode"],
                                    "ghost_fill": v["ghost_fill"], "gain": v["grade_gain"]} for k, v in rep.items()},
                     "layer_dirs": {k: str(v) for k, v in dirs.items()}}}


def st_vfx(ctx: Ctx) -> dict:
    effects = [ly for ly in ctx.compiled.layers.layers if ly.kind == "effect"]
    dirs, hashes, frames = {}, {}, {}
    for ly in effects:
        dirs[ly.id] = ctx.run_dir / "vfx" / "layers" / ly.id
        frames[ly.id] = _effect_frames(ctx, ly)
        _layer_render(ctx, ly, dirs[ly.id], frames[ly.id])
        hashes[ly.id] = content_hash({p.name: _sha(p) for p in sorted(dirs[ly.id].glob("f_*.png"))})
    return {"outputs": {}, "info": {"layer_dirs": {k: str(v) for k, v in dirs.items()}, "layer_hashes": hashes,
                                    "blender_frames": frames}}


def st_composite(ctx: Ctx) -> dict:
    _tools()
    from tools.admission import hybrid_composite as hc

    dirs = {k: Path(v) for k, v in ctx.info["VFX"]["layer_dirs"].items()}
    res = hc.run(ctx.run_dir / "preflight", Path(ctx.outputs["REPAIR"]["repaired"]), ctx.run_dir / "composite",
                 kinds=("effect",), layer_dirs=dirs, output_name="composite.mp4")
    order = [ly.id for ly in sorted(ctx.compiled.layers.layers, key=lambda ly: ly.order)]
    return {"outputs": {"composite": ctx.run_dir / "composite" / "composite.mp4",
                        "reference_with_effects": ctx.run_dir / "composite" / "reference_with_effects.mp4"},
            "info": {"order": ["raw"] + order + ["grade"],
                     "effects": {k: v.get("frames", [None])[0] for k, v in res["report"]["layers"].items()}}}


def st_grade(ctx: Ctx) -> dict:
    _tools()
    from tools.admission import finish_grade

    meta = finish_grade.run(Path(ctx.outputs["COMPOSITE"]["composite"]), ctx.run_dir / "grade", dict(ctx.compiled.grade),
                            name="final")
    return {"outputs": {"final_master": ctx.run_dir / "grade" / "final_master.mp4",
                        "final_view": ctx.run_dir / "grade" / "final.mp4"},
            "info": {"filter_chain": meta["filter_chain"], "shake": ctx.compiled.grade.get("shake")}}


def st_final_qc(ctx: Ctx) -> dict:
    import numpy as np

    from onecreations.director import media, video_qc

    _tools()
    from tools.admission import hybrid_composite as hc

    b, ref = _load_video_inputs(ctx)
    idx, om = b.passes()["object_index"], b.manifest.passes.object_index_map
    raw = media.decode_rgb(Path(ctx.outputs["LTX_GENERATE"]["raw"]))
    repaired = media.decode_rgb(Path(ctx.outputs["REPAIR"]["repaired"]))
    composite = media.decode_rgb(Path(ctx.outputs["COMPOSITE"]["composite"]))
    final = media.decode_rgb(Path(ctx.outputs["GRADE"]["final_master"]))
    alpha = {}
    for lid, d in ctx.info.get("REPAIR", {}).get("layer_dirs", {}).items():
        for p in sorted(Path(d).glob("f_*.png")):
            f = int(p.stem.split("_")[1]) - 1
            a = hc._png_rgba(p)[..., 3]
            alpha[f] = np.maximum(alpha.get(f, 0), a)
    res = video_qc.final(ctx.compiled, ref, raw, repaired, composite, final, idx, om, alpha, {})
    passed = all(v["passed"] for v in res.values())
    p = ctx.path("qc", "final.json")
    p.write_text(json.dumps({"checks": res, "passed": passed, "final_sha256": _out_sha(ctx, "GRADE", "final_master")},
                            indent=1), encoding="utf-8")
    if not passed:
        raise StageError("final QC failed: " + ", ".join(k for k, v in res.items() if not v["passed"]))
    return {"outputs": {"report": p}, "info": {"passed": True, "checks": {k: v["passed"] for k, v in res.items()}}}


def st_deliver(ctx: Ctx) -> dict:
    from onecreations.director import media

    d = ctx.run_dir / "deliverables"
    d.mkdir(parents=True, exist_ok=True)
    final = d / "final.mp4"
    shutil.copyfile(ctx.outputs["GRADE"]["final_view"], final)
    preview = d / "preview.mp4"
    subprocess.run([media.ffmpeg(), "-v", "error", "-y", "-i", str(ctx.outputs["COMPOSITE"]["reference_with_effects"]),
                    "-i", str(ctx.outputs["LTX_GENERATE"]["raw"]), "-i", str(ctx.outputs["GRADE"]["final_view"]),
                    "-filter_complex", "[0]scale=iw/2:-2[a];[1]scale=iw/2:-2[b];[2]scale=iw/2:-2[c];[a][b][c]hstack=3",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(preview)], check=True)
    return {"outputs": {"final": final, "preview": preview}, "info": {"final_sha256": _sha(final)}}


IMPLEMENTATIONS: dict[str, Callable[[Ctx], dict]] = {
    "PLAN": st_plan, "VALIDATE": st_validate, "COMPILE": st_compile, "BLENDER_BUILD": st_build,
    "CONTROL_RENDER": st_controls, "FIRST_FRAME": st_first_frame, "PREFLIGHT_QC": st_preflight_qc,
    "LTX_GENERATE": st_ltx, "POST_GENERATION_QC": st_post_qc, "REPAIR": st_repair, "VFX": st_vfx,
    "COMPOSITE": st_composite, "GRADE": st_grade, "FINAL_QC": st_final_qc, "DELIVER": st_deliver,
}


# --- executor --------------------------------------------------------------------------------------------------------

def _record_outputs(outputs: dict) -> dict:
    out = {}
    for k, v in outputs.items():
        p = Path(v)
        out[k] = {"path": str(p), "sha256": _sha(p) if p.is_file() else None}
    return out


def _cached(prev: dict | None, key: str) -> bool:
    if not prev or prev.get("status") not in ("done", "cached") or prev.get("key") != key:
        return False
    for o in prev.get("outputs", {}).values():
        p = Path(o["path"])
        if not p.is_file() or (o["sha256"] and _sha(p) != o["sha256"]):
            return False
    return True


def execute(run_dir: Path, request: str | None = None, options: Options | None = None,
            implementations: dict | None = None, from_stage: str | None = None, registry=None) -> dict:
    """Run (or resume) the stage graph in `run_dir`. Returns the execution record (also written to execution.json)."""
    from onecreations.director.registry import load_registry

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    impl = dict(IMPLEMENTATIONS, **(implementations or {}))
    exe_path = run_dir / "execution.json"
    prev = json.loads(exe_path.read_text(encoding="utf-8")) if exe_path.is_file() else None
    req_path = run_dir / "request.json"
    if req_path.is_file():
        stored = json.loads(req_path.read_text(encoding="utf-8"))["request"]
        if request is not None and request != stored:
            raise ValueError("this run directory belongs to a different request (requests are immutable)")
        request = stored
    else:
        if request is None:
            raise ValueError("a new run needs a request")
        req_path.write_text(json.dumps({"request": request, "created": _now(), "pipeline": PIPELINE_VERSION},
                                       indent=1), encoding="utf-8")
    ctx = Ctx(run_dir=run_dir, request=request, options=options or Options(), registry=registry or load_registry())
    prev_stages = {s["id"]: s for s in (prev or {}).get("stages", [])}
    force_from = STAGES.index(from_stage) if from_stage else None
    import psutil

    record = {"run_id": run_dir.name, "pipeline": PIPELINE_VERSION, "request": request, "started": _now(),
              "options": vars(ctx.options), "stages": [], "status": "running",
              "storage_free_gib_before": round(shutil.disk_usage(run_dir).free / 1024 ** 3, 2),
              "free_ram_gb_before": round(psutil.virtual_memory().available / 1024 ** 3, 2)}
    t_run = time.perf_counter()
    i = 0
    while i < len(STAGES):
        sid = STAGES[i]
        key = content_hash({"stage": sid, "v": PIPELINE_VERSION, "in": stage_inputs(sid, ctx)})
        rec = {"id": sid, "key": key, "started": _now()}
        prev_rec = prev_stages.get(sid)
        forced = force_from is not None and i >= force_from
        if not forced and _cached(prev_rec, key) and sid not in ("PLAN", "VALIDATE", "COMPILE"):
            rec.update(status="cached", finished=_now(), duration_s=0.0, outputs=prev_rec["outputs"],
                       info=prev_rec.get("info", {}))
            ctx.outputs[sid] = {k: v["path"] for k, v in prev_rec["outputs"].items()}
            ctx.info[sid] = prev_rec.get("info", {})
            record["stages"].append(rec)
            i += 1
            continue
        t0 = time.perf_counter()
        try:
            res = impl[sid](ctx)
            rec.update(status="done", outputs=_record_outputs(res.get("outputs", {})), info=res.get("info", {}))
            ctx.outputs[sid] = {k: str(v) for k, v in res.get("outputs", {}).items()}
            ctx.info[sid] = res.get("info", {})
        except RegenerateRequested as exc:
            n = ctx.attempt.get("LTX_GENERATE", 1)
            rec.update(status="failed", failure=f"regenerate requested: {exc}")
            if n <= ctx.options.technical_retries:
                ctx.attempt["LTX_GENERATE"] = n + 1
                rec["status"] = "superseded"
                rec.update(finished=_now(), duration_s=round(time.perf_counter() - t0, 2))
                record["stages"].append(rec)
                i = STAGES.index("LTX_GENERATE")
                force_from = i
                continue
        except Exception as exc:                          # noqa: BLE001 - every failure is recorded, then stops
            rec.update(status="failed", failure=f"{type(exc).__name__}: {exc}")
            if sid == "LTX_GENERATE" and ctx.attempt.get(sid, 1) <= ctx.options.technical_retries \
                    and not str(exc).startswith("only "):
                ctx.attempt[sid] = ctx.attempt.get(sid, 1) + 1
                rec["status"] = "retried"
                rec.update(finished=_now(), duration_s=round(time.perf_counter() - t0, 2))
                record["stages"].append(rec)
                continue
        rec.update(finished=_now(), duration_s=round(time.perf_counter() - t0, 2))
        record["stages"].append(rec)
        if rec["status"] == "failed":
            record["status"] = "failed"
            record["failed_stage"] = sid
            record["failure"] = rec["failure"]
            break
        i += 1
    else:
        record["status"] = "succeeded"
    for sid in STAGES:
        if not any(s["id"] == sid for s in record["stages"]):
            record["stages"].append({"id": sid, "status": "not_run"})
    record["finished"] = _now()
    record["wall_s"] = round(time.perf_counter() - t_run, 1)
    record["storage_free_gib_after"] = round(shutil.disk_usage(run_dir).free / 1024 ** 3, 2)
    exe_path.write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    write_report(run_dir, record, ctx)
    return record


def write_report(run_dir: Path, record: dict, ctx: Ctx) -> None:
    """Machine-readable report.json and human-readable report.md in deliverables/ (also for failed runs)."""
    d = run_dir / "deliverables"
    d.mkdir(parents=True, exist_ok=True)
    plan = ctx.plan.model_dump(mode="json") if ctx.plan else None
    rep = {"status": record["status"], "run_id": record["run_id"], "request": record["request"], "plan": plan,
           "shot_spec": ctx.spec.model_dump(mode="json") if ctx.spec else None,
           "assets": ({"characters": plan["characters"], "weapons": plan["weapons"], "environment": plan["environment"],
                       "actions": plan["actions"], "camera": [plan["camera"], plan["camera_variant"]],
                       "look": plan["look"], "vfx": plan["vfx"]} if plan else None),
           "stages": [{k: s.get(k) for k in ("id", "status", "duration_s", "failure")} for s in record["stages"]],
           "qc": {k: ctx.info.get(k) for k in ("PREFLIGHT_QC", "POST_GENERATION_QC", "FINAL_QC")},
           "repair": ctx.info.get("REPAIR"), "ltx": ctx.info.get("LTX_GENERATE"), "wall_s": record.get("wall_s"),
           "deliverables": ({"final": str(d / "final.mp4"), "preview": str(d / "preview.mp4")}
                            if record["status"] == "succeeded" else None),
           "final_sha256": ctx.info.get("DELIVER", {}).get("final_sha256"),
           "storage_free_gib": [record.get("storage_free_gib_before"), record.get("storage_free_gib_after")]}
    (d / "report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    lines = [f"# OneCreations run {record['run_id']}: {record['status'].upper()}", "", f"Request: {record['request']}",
             "", "| Stage | Status | Seconds | Note |", "|---|---|---|---|"]
    for s in record["stages"]:
        lines.append(f"| {s['id']} | {s.get('status')} | {s.get('duration_s', '')} | {s.get('failure', '') or ''} |")
    if plan:
        lines += ["", "## Director decisions", ""]
        lines += [f"- {x['slot']}: {x['choice']} ({x['source']}" + (f", '{x['evidence']}'" if x.get("evidence") else "")
                  + ")" for x in plan["decisions"]]
        lines += [f"- WARNING: {w}" for w in plan["warnings"]]
    if record["status"] == "succeeded":
        lines += ["", f"Final video: {d / 'final.mp4'}", f"Preview (reference | raw | final): {d / 'preview.mp4'}"]
    else:
        lines += ["", f"Not delivered: {record.get('failed_stage')} - {record.get('failure')}"]
    (d / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def new_run_dir(root: Path | None = None, run_id: str | None = None) -> Path:
    root = Path(root or DATA_ROOT / "runs")
    rid = run_id or dt.datetime.now().strftime("run_%Y%m%d_%H%M%S")
    return root / rid
