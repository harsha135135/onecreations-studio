# OneCreations Studio — working instructions

Start every session by reading `STATUS.md` (current phase, next milestone, hard rules), then
`docs/decisions/ADR-0001-hardware-and-compute-strategy.md` and `docs/contracts.md` (conventions every module follows). The original research document is
`docs/research/2026-10-01-decision-v1.md`; the ADR overrides it where they conflict.

## Machines

- **Windows 11 desktop** (RTX 4070 12 GB, i7-14700K with iGPU, 32 GB RAM): does all GPU work — Blender, ComfyUI, admission ladders, local training. Runs GPU jobs natively on Windows, not WSL2.
- **macOS laptop**: docs, contracts, tooling, CPU-only tests. Has no CUDA; never claim a GPU result from it.

## Rules

- **Money:** never start, resume or extend paid compute (GPU pods, cloud storage, paid APIs) without first running
  `uv run python tools/budget/ledger.py check --gpu <type> --hours <h>` **and** getting the owner's explicit go-ahead
  in the current session. Log every charge with `ledger.py add`. Hard ceiling ₹15,000 total; Gate A ₹5,000 until the owner unlocks Gate B.
- **Measure, don't assume.** Label figures as measured / published / arithmetic / proposed. Record admission runs with
  `tools/admission/monitor.py` into `admission_records/`. Report failures and all seeds, not just the best.
- **4070-first:** develop, debug and train locally whatever fits; rent H100 only for the LTX-2.5 adapter after gate G4.
- **Model choice by benchmark quality/controllability**, not by fit. Wan2.1-VACE-1.3B is an experiment, not the primary.
- **No large files in Git:** weights, datasets, renders, caches and latents live under the data root (default `D:\onecreations\`),
  referenced by hash in `model_registry/` and manifests.
- **Pin upstream repos** (ComfyUI, ComfyUI-LTXVideo, LTX-2 trainer, musubi-tuner, ai-toolkit) to commit SHAs in `model_registry/models.yaml`.
- **Authorship:** all commits, PRs and docs are by Harshavardhan M (`harsha135135`). Never add `Co-Authored-By` lines,
  "Generated with" footers or any AI attribution.
- **Conventions are contracts:** camera_to_world in Blender camera axes, quaternions wxyz, planar depth, exact rational
  time (`docs/contracts.md`). Change a contract → regenerate `schemas/` (`uv run onecreations schemas export`) and keep tests green.
- **Blender scripts** in `integrations/blender/` run inside Blender with bpy + stdlib + numpy only; they may import
  `onecreations.timebase`, `hashing`, `geometry`, `camera.trajectory` but never pydantic-based modules.
- **Update `STATUS.md`** at the end of each session (header, milestones, session log), then commit and push.

## Commands

```bash
uv sync                                  # install deps (numpy, pydantic, psutil, pyyaml, pytest)
uv run pytest -q                         # unit + headless-Blender tests (run on both machines)
uv run pytest -q -m blender              # Blender contract tests only (needs Blender 4.5; ONECREATIONS_BLENDER overrides)
uv run onecreations --help               # validate-shot, schemas, camera, blender subcommands
uv run python tools/budget/ledger.py status
uv run python tools/admission/monitor.py --label ltx25-rung1 -- <command that runs the job>
uv run python tools/inspect_safetensors.py <file.safetensors> --lora-summary
uv run python tools/registry/hash_files.py <files...>
powershell -ExecutionPolicy Bypass -File tools\windows\check_env.ps1   # Windows only
```
