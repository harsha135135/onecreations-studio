# Runbook: prompt → final video (D2 pipeline)

The D2 executor (`src/onecreations/director/pipeline.py`) runs a supported request end to end on the Windows desktop:
Blender builds the scene, LTX-2.5 generates, the Blender-owned weapon and the effects are composited, the grade is
applied and QC decides whether the run succeeded. The supported domain is the Showcase class only (see
`docs/decisions/ADR-0002-prompt-directed-production.md` §13 and `library/registry.yaml`).

## Before a run

1. **Close Chrome and other large apps.** RAM is the binding resource: LTX needs about 20 GB free, and the
   `LTX_GENERATE` stage refuses to start below `Options.min_free_ram_gb` (20.0 GB, pre-registered).
2. Check `G:` has room: a run writes about 1.5–2 GB (blend, passes, reference renders, layers, videos).
3. Optional: `uv run onecreations generate "PROMPT" --dry-run` shows every director decision, the events, the policies
   and the layers without starting a process. `--preflight DIR` builds and checks the scene and stops before LTX.

## Run

```powershell
uv run onecreations generate "Create a cinematic shot of a horned Asura attacking an ascetic defender with a heavy mace in an ancient ruined temple at dusk. The defender guards with a trident. Use a low orbit and push-in. Add dust, debris, sparks and floor cracks on impact." --run-id my_run
```

- Output root: `G:\onecreations\runs\<run_id>` (`--output ROOT` changes the root; `ONECREATIONS_DATA` changes the data root).
- The command prints each stage's status and exits 0 only when FINAL_QC passed and the deliverables were written.
- Deliverables: `deliverables/final.mp4` (the graded shot), `deliverables/preview.mp4` (Blender reference with effects |
  raw LTX | final, half scale), `deliverables/report.json` and `report.md`.

## Stage graph

`PLAN → VALIDATE → COMPILE → BLENDER_BUILD → CONTROL_RENDER → FIRST_FRAME → PREFLIGHT_QC → LTX_GENERATE →
POST_GENERATION_QC → REPAIR → VFX → COMPOSITE → GRADE → FINAL_QC → DELIVER`

| Stage | Proven tool it runs | Writes |
|---|---|---|
| PLAN / VALIDATE / COMPILE | interpreter, planner, validator, compiler (D1) | `director_plan.json`, `shot_spec.json`, `compiled_shot.json` |
| BLENDER_BUILD | `build_showcase_scene.py --config preflight/scene_build.json` | `preflight/scene.blend`, `preflight/shot_spec.json` |
| CONTROL_RENDER | `oc_export --passes --probes [--material-index]`, `make_controls.py`, `render_reference.py` (sharp + 0.5-frame motion blur) | `preflight/export/`, `controls/depth_control.mp4`, `preflight/reference_*.mp4` |
| FIRST_FRAME | `render_stills.py` frame 1 at 1024 spp | `controls/first_frame.png` |
| PREFLIGHT_QC | `qc.evaluate_preflight`, `executor.write_masks` | `qc/preflight.json`, `preflight/masks/` |
| LTX_GENERATE | `monitor.py` → `comfy_run.py` → ComfyUI with the compiled workflow | `generation/raw.mp4`, `records.jsonl` (telemetry), `report.json` |
| POST_GENERATION_QC | `video_qc.post_generation` + `decide` | `qc/post_generation.json` |
| REPAIR | `render_layers.py` (protected layers) + `hybrid_composite` (protected pass) | `repair/repaired.mp4`, `repair/layers/` |
| VFX | `render_layers.py` (effect layers, frames from the CONTACT trigger) | `vfx/layers/` |
| COMPOSITE | `hybrid_composite` (effect pass) | `composite/composite.mp4` |
| GRADE | `finish_grade.py` with `CompiledShot.grade` | `grade/final_master.mp4`, `grade/final.mp4` |
| FINAL_QC | `video_qc.final` | `qc/final.json` |
| DELIVER | copy + preview encode | `deliverables/` |

## Failures and resuming

- An unsupported or invalid request stops at PLAN / VALIDATE (nothing is built). A failed preflight check stops before
  LTX. A post-generation check whose `on_fail` is `fail` stops the run; `regenerate` (only `video_valid`,
  `output_integrity`) allows one more generation with the same seed; `repair` is handled by the protection policy.
- One technical LTX retry is allowed (not for the RAM guard). There is no seed search.
- `uv run onecreations generate --resume G:\onecreations\runs\<run_id>` resumes: a stage whose input key and recorded
  output hashes are unchanged is reported `cached` and not rerun, so a late failure never reruns Blender or LTX.
  `--from-stage GRADE` forces that stage and everything after it. The request of a run directory cannot change.
- `execution.json` holds every stage's key, status, times, outputs (with SHA-256) and failure reason.

## Rehearsal (no LTX)

`uv run python tools/director/rehearse.py "PROMPT" --raw <earlier raw.mp4>` runs every stage except LTX, which copies
an existing raw generation of the same shot class. Use it to prove the deterministic stages before spending a
generation. A rehearsal run directory is named `rehearsal_*` and is never a result.
