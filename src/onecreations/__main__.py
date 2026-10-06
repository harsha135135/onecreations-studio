"""OneCreations command line.

    onecreations validate-shot examples/diagnostic [--shot ID] [--json]
    onecreations schemas export|check
    onecreations camera stats FILE                      (.npz, .csv or an export bundle directory)
    onecreations camera import-colmap images.txt --fps 24 --out traj.npz
    onecreations camera retarget FILE --src X,Y,Z,YAW --dst X,Y,Z,YAW [--scale S] [--time-scale T] --out traj.npz
                                      [--proxies proxies.json --clearance 0.15]
    onecreations blender info
    onecreations blender build-diagnostic --out diag.blend
    onecreations blender export SCENE.blend --out DIR [--passes] [--probes] [--timewarp tw.json] [--camera NAME]
    onecreations blender import-camera SCENE.blend --samples FILE --save OUT.blend [--intrinsics JSON]
    onecreations blender visualize --samples FILE --save OUT.blend [--blend SCENE.blend] [--intrinsics JSON] ...
    onecreations director plan "PROMPT" [--spec-out spec.json] [--shot-id ID]
    onecreations director validate SPEC.json
    onecreations director compile SPEC.json [--out compiled.json]
    onecreations generate "PROMPT" --dry-run [--json]         (or --spec SPEC.json instead of a prompt)
    onecreations generate "PROMPT" --preflight DIR [--samples 64]   (Blender controls + first frame + masks + QC; no LTX)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _load_any_trajectory(path: str):
    from onecreations.blender_bundle import load_bundle
    from onecreations.shotpkg.project import load_trajectory
    p = Path(path)
    if p.is_dir():
        return load_bundle(p).camera_trajectory()
    return load_trajectory(p)


def cmd_validate_shot(args) -> int:
    from onecreations.shotpkg import event_schedule, has_errors, load_project, validate_shot
    ctx, shots, load_issues = load_project(args.project)
    selected = {args.shot: shots[args.shot]} if args.shot else shots
    report = {"load_issues": [i.to_dict() for i in load_issues], "shots": {}}
    failed = bool([i for i in load_issues if i.severity == "error"])
    for sid, shot in selected.items():
        issues = validate_shot(shot, ctx)
        failed |= has_errors(issues)
        report["shots"][sid] = {"issues": [i.to_dict() for i in issues], "events": event_schedule(shot, ctx)}
    if args.json:
        _print(report)
    else:
        for i in load_issues:
            print(f"[{i.severity.upper()}] {i.code}: {i.message}")
        for sid, r in report["shots"].items():
            print(f"shot {sid}: {sum(i['severity'] == 'error' for i in r['issues'])} errors, "
                  f"{sum(i['severity'] == 'warning' for i in r['issues'])} warnings")
            for i in r["issues"]:
                print(f"  [{i['severity'].upper()}] {i['code']}: {i['message']}")
            for e in r["events"]:
                print(f"  event {e['event']} ({e['type']}): source {e['source_time']} s → output {e['output_time']} s, "
                      f"frame {e['frame_position']} (nearest {e['nearest_frame']})")
    return 1 if failed else 0


def cmd_schemas(args) -> int:
    from onecreations.contracts.schema_export import stale_schemas, write_schemas
    if args.action == "export":
        for p in write_schemas():
            print(p)
        return 0
    stale = stale_schemas()
    if stale:
        print("stale schemas (run `onecreations schemas export`):", ", ".join(stale))
        return 1
    print("schemas up to date")
    return 0


def _parse_anchor(text: str):
    from onecreations.camera.retarget import Anchor
    parts = [float(v) for v in text.split(",")]
    if len(parts) not in (3, 4):
        raise SystemExit("anchors are X,Y,Z or X,Y,Z,YAW_DEG")
    return Anchor(tuple(parts[:3]), parts[3] if len(parts) == 4 else 0.0)


def cmd_camera(args) -> int:
    if args.camera_cmd == "stats":
        from onecreations.camera.analysis import preview_metadata
        _print(preview_metadata(_load_any_trajectory(args.file), Path(args.file).stem))
        return 0
    if args.camera_cmd == "import-colmap":
        from onecreations.camera.io_colmap import images_to_trajectory, parse_images_txt
        from onecreations.timebase import FrameRate
        traj = images_to_trajectory(parse_images_txt(args.images), FrameRate.from_value(args.fps), args.order)
        traj.save_npz(args.out)
        print(f"{len(traj)} poses → {args.out} (scale unknown, up unaligned: normalize before metric use)")
        return 0
    if args.camera_cmd == "retarget":
        from onecreations.camera.retarget import clearance_report, proxies_from_dicts, retarget
        out = retarget(_load_any_trajectory(args.file), _parse_anchor(args.src), _parse_anchor(args.dst),
                       args.scale, args.time_scale)
        out.save_npz(args.out)
        print(f"retargeted → {args.out}")
        if args.proxies:
            rep = clearance_report(out, proxies_from_dicts(json.loads(Path(args.proxies).read_text())), args.clearance)
            _print(rep)
            return 0 if rep["ok"] else 2
        return 0
    raise AssertionError(args.camera_cmd)


def cmd_blender(args) -> int:
    from onecreations import blender_bridge as bb
    if args.blender_cmd == "info":
        exe = bb.find_blender()
        if exe is None:
            print(f"Blender not found (set {bb.ENV_VAR})")
            return 1
        v = bb.blender_version(exe)
        print(f"{exe}\nversion {v} ({'pinned series' if bb.is_pinned(v) else 'NOT the pinned ' + bb.PINNED_SERIES + ' series'})")
        return 0
    if args.blender_cmd == "build-diagnostic":
        bb.run_script("build_diagnostic_scene.py", ["--out", args.out])
        print(args.out)
        return 0
    if args.blender_cmd == "export":
        from onecreations.blender_bundle import load_bundle
        extra = ["--out", args.out, "--shot-id", args.shot_id]
        for flag in ("passes", "probes"):
            if getattr(args, flag):
                extra.append(f"--{flag}")
        for opt in ("camera", "timewarp", "fps", "duration"):
            if getattr(args, opt):
                extra += [f"--{opt}", getattr(args, opt)]
        bb.run_script("oc_export.py", extra, blend=args.blend)
        m = load_bundle(args.out).manifest
        print(f"bundle OK: {m.shot.frame_count} frames, Blender {m.blender_version}, content {m.content_sha256[:12]}"
              + (f", depth {m.passes.depth.measured_convention}" if m.passes else ""))
        return 0
    if args.blender_cmd == "import-camera":
        extra = ["--samples", args.samples, "--save", args.save, "--camera-name", args.camera_name]
        if args.intrinsics:
            extra += ["--intrinsics", args.intrinsics]
        bb.run_script("oc_import_camera.py", extra, blend=args.blend)
        print(args.save)
        return 0
    if args.blender_cmd == "visualize":
        extra = ["--samples", args.samples, "--save", args.save, "--frustums", str(args.frustums)]
        for opt in ("intrinsics", "target", "summary", "name"):
            if getattr(args, opt):
                extra += [f"--{opt}", getattr(args, opt)]
        if args.velocity:
            extra.append("--velocity")
        bb.run_script("oc_visualize_trajectory.py", extra, blend=args.blend)
        print(args.save)
        return 0
    raise AssertionError(args.blender_cmd)


def _load_spec(path: str):
    from onecreations.contracts.director import ShotSpec
    return ShotSpec.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def cmd_director(args) -> int:
    from onecreations.director.compiler import CompileError, compile_shot
    from onecreations.director.executor import plan_request, summarize
    from onecreations.director.registry import load_registry
    from onecreations.director.validate import validate_spec
    reg = load_registry()
    if args.director_cmd == "plan":
        plan, spec = plan_request(args.prompt, reg, args.shot_id)
        _print(plan.model_dump(mode="json"))
        if spec is not None and args.spec_out:
            Path(args.spec_out).write_text(spec.model_dump_json(indent=2), encoding="utf-8")
            print(f"ShotSpec -> {args.spec_out}")
        return 0 if plan.supported else 2
    spec = _load_spec(args.spec)
    if args.director_cmd == "validate":
        issues = validate_spec(spec, reg)
        for i in issues:
            print(f"[{i.severity.upper()}] {i.code}: {i.message}")
        bad = any(i.severity == "error" for i in issues)
        print("INVALID" if bad else "valid")
        return 1 if bad else 0
    try:
        compiled = compile_shot(spec, reg)
    except CompileError as exc:
        for i in exc.issues:
            print(f"[{i.severity.upper()}] {i.code}: {i.message}")
        return 1
    if args.out:
        Path(args.out).write_text(compiled.model_dump_json(indent=1), encoding="utf-8")
        print(f"CompiledShot -> {args.out}")
    else:
        _print(summarize(compiled))
    return 0


def cmd_generate(args) -> int:
    from onecreations.director.compiler import compile_shot
    from onecreations.director.executor import dry_run, plan_request, preflight
    from onecreations.director.registry import load_registry
    if not (args.dry_run or args.preflight):
        print("full prompt -> final video is not orchestrated yet (D1): use --dry-run or --preflight DIR")
        return 2
    if bool(args.prompt) == bool(args.spec):
        print("give a PROMPT or --spec SPEC.json")
        return 2
    reg = load_registry()
    spec = _load_spec(args.spec) if args.spec else None
    if args.dry_run:
        out = dry_run(request=args.prompt, spec=spec, reg=reg, shot_id=args.shot_id)
        if args.json:
            _print(out)
        else:
            _print_dry_run(out)
        return {"ok": 0, "invalid": 1, "unsupported": 2}[out["status"]]
    if spec is None:
        plan, spec = plan_request(args.prompt, reg, args.shot_id)
        if spec is None:
            _print({"supported": False, "unsupported": plan.unsupported, "warnings": plan.warnings})
            return 2
    report = preflight(compile_shot(spec, reg), Path(args.preflight), samples=args.samples)
    summary = {k: report[k] for k in ("shot_id", "out_dir", "timings", "stopped_before")}
    summary["qc_passed"] = report["qc"]["passed"]
    _print(summary)
    return 0 if report["qc"]["passed"] else 1


def _print_dry_run(out: dict) -> None:
    plan = out.get("plan")
    if plan:
        print(f"interpreter {plan['interpreter']}: supported={plan['supported']}")
        for d in plan["decisions"]:
            ev = f" ({d['evidence']!r})" if d.get("evidence") else ""
            note = f" - {d['note']}" if d.get("note") else ""
            print(f"  {d['slot']:<34} {d['choice']:<28} {d['source']}{ev}{note}")
        for w in plan["warnings"]:
            print(f"  WARNING: {w}")
        for u in plan["unsupported"]:
            print(f"  UNSUPPORTED: {u}")
    for i in out.get("issues", []):
        print(f"  [{i['severity'].upper()}] {i['code']}: {i['message']}")
    c = out.get("compiled")
    if not c:
        print(f"status: {out['status']}")
        return
    w, h = c["resolution"]
    print(f"shot {c['shot_id']}: {c['frames']} frames @ {c['fps']} fps, {w}x{h}, engine {c['engine']}")
    print("events: " + ", ".join(f"{k}={v}" for k, v in c["events"].items()))
    for k, o in c["objects"].items():
        print(f"  {k:<14} {o['kind']:<17} {o['asset']:<22} {o['policy']}")
    parts = []
    for ly in c["layers"]:
        trig = ly["trigger"]
        parts.append(ly["id"] + (f"@{trig['phase']}.{trig['edge']}" if trig else ""))
    print("layers: " + ", ".join(parts))
    g = c["generation"]
    print(f"generation: {g['backend']}, seed {g['seed']}, {g['steps']} steps")
    print(f"prompt: {g['prompt']}")
    print("stages: " + " -> ".join(s["id"] + ("" if s["implemented"] else "(not in D1)") for s in c["stages"]))
    print("dry run: no process was started (no Blender, no LTX)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="onecreations", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate-shot")
    v.add_argument("project")
    v.add_argument("--shot")
    v.add_argument("--json", action="store_true")

    s = sub.add_parser("schemas")
    s.add_argument("action", choices=["export", "check"])

    c = sub.add_parser("camera")
    csub = c.add_subparsers(dest="camera_cmd", required=True)
    st = csub.add_parser("stats")
    st.add_argument("file")
    ic = csub.add_parser("import-colmap")
    ic.add_argument("images")
    ic.add_argument("--fps", required=True)
    ic.add_argument("--order", choices=["name", "image_id"], default="name")
    ic.add_argument("--out", required=True)
    rt = csub.add_parser("retarget")
    rt.add_argument("file")
    rt.add_argument("--src", required=True)
    rt.add_argument("--dst", required=True)
    rt.add_argument("--scale", type=float, default=1.0)
    rt.add_argument("--time-scale", type=float, default=1.0)
    rt.add_argument("--out", required=True)
    rt.add_argument("--proxies")
    rt.add_argument("--clearance", type=float, default=0.15)

    b = sub.add_parser("blender")
    bsub = b.add_subparsers(dest="blender_cmd", required=True)
    bsub.add_parser("info")
    bd = bsub.add_parser("build-diagnostic")
    bd.add_argument("--out", required=True)
    be = bsub.add_parser("export")
    be.add_argument("blend")
    be.add_argument("--out", required=True)
    be.add_argument("--shot-id", default="adhoc")
    be.add_argument("--camera")
    be.add_argument("--timewarp")
    be.add_argument("--fps")
    be.add_argument("--duration")
    be.add_argument("--passes", action="store_true")
    be.add_argument("--probes", action="store_true")
    bi = bsub.add_parser("import-camera")
    bi.add_argument("blend")
    bi.add_argument("--samples", required=True)
    bi.add_argument("--save", required=True)
    bi.add_argument("--intrinsics")
    bi.add_argument("--camera-name", default="OC_Camera_Import")
    bv = bsub.add_parser("visualize")
    bv.add_argument("--blend")
    bv.add_argument("--samples", required=True)
    bv.add_argument("--save", required=True)
    bv.add_argument("--intrinsics")
    bv.add_argument("--frustums", type=int, default=8)
    bv.add_argument("--target")
    bv.add_argument("--velocity", action="store_true")
    bv.add_argument("--summary")
    bv.add_argument("--name")

    d = sub.add_parser("director")
    dsub = d.add_subparsers(dest="director_cmd", required=True)
    dp = dsub.add_parser("plan")
    dp.add_argument("prompt")
    dp.add_argument("--spec-out")
    dp.add_argument("--shot-id", default="d1_shot")
    dv = dsub.add_parser("validate")
    dv.add_argument("spec")
    dc = dsub.add_parser("compile")
    dc.add_argument("spec")
    dc.add_argument("--out")

    g = sub.add_parser("generate")
    g.add_argument("prompt", nargs="?")
    g.add_argument("--spec")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--preflight", metavar="DIR")
    g.add_argument("--samples", type=int, default=64)
    g.add_argument("--shot-id", default="d1_shot")
    g.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    handler = {"validate-shot": cmd_validate_shot, "schemas": cmd_schemas, "camera": cmd_camera,
               "blender": cmd_blender, "director": cmd_director, "generate": cmd_generate}[args.cmd]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
