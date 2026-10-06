"""Top-level director entry points: dry run and the deterministic preflight (everything up to, never including, LTX).

    request -> interpret -> DirectorPlan -> plan_to_spec -> ShotSpec -> validate -> compile -> CompiledShot
            -> [preflight] Blender build -> control passes + depth control -> first frame -> masks -> preflight QC

`dry_run` never starts a process. `preflight` runs only proven deterministic stages (Blender, ffmpeg); the generation,
repair, compositing and grade stages are reported as the next stages but are not executed in D1.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from onecreations.blender_bridge import REPO_ROOT
from onecreations.contracts.director import CompiledShot, DirectorPlan, ShotSpec
from onecreations.director.compiler import compile_shot
from onecreations.director.interpreter import interpret
from onecreations.director.planner import plan_to_spec
from onecreations.director.registry import Registry, load_registry
from onecreations.director.validate import validate_spec


def plan_request(request: str, reg: Registry, shot_id: str = "d1_shot") -> tuple[DirectorPlan, ShotSpec | None]:
    plan = interpret(request, reg)
    return plan, (plan_to_spec(plan, reg, shot_id) if plan.supported else None)


def summarize(compiled: CompiledShot) -> dict:
    return {
        "shot_id": compiled.shot_id, "engine": compiled.engine,
        "frames": compiled.frames, "fps": compiled.fps, "resolution": list(compiled.resolution),
        "events": {e.name: e.frame for e in compiled.events},
        "objects": {o.id: {"kind": o.kind, "asset": o.asset, "oc_ids": o.oc_ids, "mask": o.mask_source,
                           "mask_separable": o.mask_separable, "policy": f"appearance={o.policy.appearance}, "
                           f"geometry={o.policy.geometry}" + (f", rule={o.policy.rule}" if o.policy.rule else ""),
                           "protected_layer": o.protected_layer} for o in compiled.semantic_objects},
        "camera": compiled.camera_move,
        "layers": [{"id": ly.id, "kind": ly.kind, "trigger": ly.trigger.model_dump() if ly.trigger else None,
                    "duration_frames": ly.duration_frames} for ly in compiled.layers.layers],
        "generation": {"backend": compiled.generation.backend, "workflow": compiled.generation.workflow,
                       "seed": compiled.generation.seed, "steps": compiled.generation.steps,
                       "prompt": compiled.generation.prompt},
        "grade_shake": compiled.grade.get("shake"),
        "stages": [{"id": s.id, "implemented": s.implemented, "runs_in_dry_run": s.in_dry_run, "notes": s.notes}
                   for s in compiled.stages],
        "notes": compiled.notes,
    }


def dry_run(request: str | None = None, spec: ShotSpec | None = None, reg: Registry | None = None,
            shot_id: str = "d1_shot") -> dict:
    """Interpret / validate / compile and describe what would run. Starts no process (no Blender, no LTX)."""
    reg = reg or load_registry()
    out: dict = {"mode": "dry_run", "executed_processes": []}
    if request is not None:
        plan, spec = plan_request(request, reg, shot_id)
        out["plan"] = plan.model_dump(mode="json")
        if spec is None:
            out["status"] = "unsupported"
            return out
    issues = validate_spec(spec, reg)
    out["spec"] = spec.model_dump(mode="json")
    out["issues"] = [i.to_dict() for i in issues]
    if any(i.severity == "error" for i in issues):
        out["status"] = "invalid"
        return out
    out["compiled"] = summarize(compile_shot(spec, reg))
    out["status"] = "ok"
    return out


def _write_png_gray(mask: np.ndarray, path: Path) -> None:
    h, w = mask.shape
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}",
                    "-i", "-", "-frames:v", "1", str(path)], input=(mask.astype(np.uint8) * 255).tobytes(), check=True)


def write_masks(compiled: CompiledShot, bundle_dir: Path, out_dir: Path) -> dict:
    """Per-semantic-object masks from the object-index pass at the key events (the MaskProvider of D1)."""
    from onecreations.blender_bundle import load_bundle

    passes = load_bundle(bundle_dir).passes()
    idx = passes["object_index"]
    mat = passes["material_index"] if "material_index" in passes else None
    ev = {e.name.split(".")[1]: e.frame for e in compiled.events if e.name.startswith("strike.")}
    frames = sorted({0, ev["APEX"], ev["CONTACT"], compiled.frames - 1})
    out_dir.mkdir(parents=True, exist_ok=True)
    index = {}
    for o in compiled.semantic_objects:
        if o.mask_source != "object_index_pass" or not o.pass_indices:
            continue
        files = {}
        for f in frames:
            m = np.isin(idx[f], o.pass_indices)
            p = out_dir / f"{o.id.lower()}_f{f:02d}.png"
            _write_png_gray(m, p)
            files[str(f)] = {"file": p.name, "pixels": int(m.sum())}
        index[o.id] = {"pass_indices": o.pass_indices, "separable": o.mask_separable, "frames": files}
        if o.material_masks and mat is not None:       # per-part masks: object AND material-index group
            parts = {}
            for part, group in o.material_masks.items():
                pf = {}
                for f in frames:
                    m = np.isin(idx[f], o.pass_indices) & (mat[f] == group)
                    p = out_dir / f"{o.id.lower()}_{part}_f{f:02d}.png"
                    _write_png_gray(m, p)
                    pf[str(f)] = {"file": p.name, "pixels": int(m.sum())}
                parts[part] = {"material_index": group, "frames": pf}
            index[o.id]["parts"] = parts
    (out_dir / "masks.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return index


def preflight(compiled: CompiledShot, out_dir: Path, samples: int = 64, device: str = "OPTIX") -> dict:
    """Build the compiled shot in Blender and render its control inputs, first frame and masks; run preflight QC.
    Stops before generation."""
    from onecreations import blender_bridge as bb
    from onecreations.director.qc import evaluate_preflight

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "compiled_shot.json").write_text(compiled.model_dump_json(indent=1), encoding="utf-8")
    cfg = out_dir / "scene_build.json"
    cfg.write_text(json.dumps(compiled.scene_build, indent=1), encoding="utf-8")
    t = {}
    t0 = time.perf_counter()
    blend = out_dir / "scene.blend"
    bb.run_script("build_showcase_scene.py", ["--out", blend, "--spec", out_dir / "shot_spec.json", "--config", cfg],
                  timeout=1800)
    t["build_s"] = round(time.perf_counter() - t0, 1)
    t0 = time.perf_counter()
    bb.run_script("oc_export.py", ["--out", out_dir / "export", "--passes", "--probes", "--shot-id", compiled.shot_id],
                  blend=blend, timeout=3600)
    t["export_s"] = round(time.perf_counter() - t0, 1)
    t0 = time.perf_counter()
    subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "admission" / "make_controls.py"), str(out_dir / "export"),
                    "--out", str(out_dir / "depth_control.mp4")], check=True, capture_output=True)
    t["control_s"] = round(time.perf_counter() - t0, 1)
    t0 = time.perf_counter()
    bb.run_script("render_stills.py", ["--out-dir", out_dir / "first_frame_render", "--frames", "1", "--samples",
                                       str(samples), "--device", device], blend=blend, timeout=3600)
    shutil.copyfile(out_dir / "first_frame_render" / "still_0001.png", out_dir / "first_frame.png")
    t["first_frame_s"] = round(time.perf_counter() - t0, 1)
    masks = write_masks(compiled, out_dir / "export", out_dir / "masks")
    built = json.loads((out_dir / "shot_spec.json").read_text(encoding="utf-8"))
    qc = evaluate_preflight(compiled, out_dir / "export", out_dir / "first_frame.png", built)
    report = {"mode": "preflight", "shot_id": compiled.shot_id, "out_dir": str(out_dir), "timings": t,
              "first_frame_samples": samples, "masks": {k: v["pass_indices"] for k, v in masks.items()},
              "qc": qc, "stopped_before": "generate (LTX not invoked)"}
    (out_dir / "preflight_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report
