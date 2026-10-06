"""D2 rehearsal: run the full stage graph for a prompt with every stage real except LTX_GENERATE, which copies an
existing raw generation of the same shot class (default: Showcase v1 run 1). Proves the deterministic stages
(Blender, controls, QC, repair, effects, composite, grade, final QC, delivery) end to end before a real generation is
spent. A rehearsal is never a D2 result: its run directory is named `rehearsal_*` and its report says so.

    uv run python tools/director/rehearse.py "PROMPT" --raw <raw.mp4> [--run-id rehearsal_x]
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
from pathlib import Path

from onecreations.director import pipeline

SHOWCASE_RAW = pipeline.DATA_ROOT / "experiments" / "2026-10-06_showcase-v1-run1" / "showcase_v1" / \
    "showcase_v1_00001_.mp4"


def fake_ltx(raw: Path):
    def st(ctx: pipeline.Ctx) -> dict:
        out = ctx.path("generation", "raw.mp4")
        shutil.copyfile(raw, out)
        return {"outputs": {"raw": out}, "info": {"rehearsal": True, "source_raw": str(raw),
                                                  "note": "LTX not invoked: rehearsal copy of an earlier generation"}}
    return st


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("prompt")
    ap.add_argument("--raw", type=Path, default=SHOWCASE_RAW)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--first-frame-samples", type=int, default=1024)
    a = ap.parse_args(argv)
    rid = a.run_id or dt.datetime.now().strftime("rehearsal_%Y%m%d_%H%M%S")
    run_dir = pipeline.new_run_dir(None, rid)
    if run_dir.exists() and not a.resume:
        raise SystemExit(f"{run_dir} exists (use --resume)")
    rec = pipeline.execute(run_dir, request=a.prompt, options=pipeline.Options(first_frame_samples=a.first_frame_samples),
                           implementations={"LTX_GENERATE": fake_ltx(a.raw)})
    for st in rec["stages"]:
        print(f"  {st['id']:<20} {st['status']:<10} {st.get('duration_s', '')}  {st.get('failure', '') or ''}")
    print(f"rehearsal {rec['run_id']}: {rec['status'].upper()} in {rec['wall_s']} s -> {run_dir}")
    return 0 if rec["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
