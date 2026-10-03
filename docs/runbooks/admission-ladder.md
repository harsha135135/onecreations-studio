# Runbook M3 — Inference admission ladders (gate G2)

Purpose: **measure**, on this desktop (RTX 4070 12 GB, 32 GB RAM), whether each candidate's real controlled
graph runs reliably — and record the envelope. Source procedure: v1 §18; decisions: ADR-0001 D3.

**Do not assume LTX-2.5 fails on 32 GB RAM. Run it.** The original order was FLUX.2-klein-4B → Wan2.1-VACE-1.3B → LTX-2.5.
**Owner decision 2026-10-02: LTX-2.5 rungs 1–2 go first**, because the most valuable fact now is whether LTX-2.5 works on this machine
and what its measured bottleneck is. FLUX and VACE follow.

## Before every rung

- Fresh reboot or at least: close browsers, Blender, launchers, anything on the GPU. `nvidia-smi` idle ≈ a few hundred MB.
- Note free RAM. The goal is a clean, repeatable baseline.
- **Windows Update:** nothing pending that would reboot. **Pause updates** (Settings → Windows Update → Pause) for the run session.
  Driver updates stay hidden or unselected (see `docs/measurements/`).
- **PCIe:** the monitor records the link under load and flags anything below Gen4 x16 (`--expect-pcie`). If x4 returns repeatedly,
  stop and investigate (reseat or slot check) before trusting offload timings.
- Models from the official sources, hashes recorded (`uv run python tools/registry/hash_files.py ...`) in `model_registry/models.yaml`.
- **Downloads are staged per rung.** Download only what the rung's graph needs, into `G:\onecreations\models\…`, with
  `tools\windows\oc_env.ps1` dot-sourced so no cache lands on C:.

## How to record

Each run is `monitor.py` wrapping `comfy_run.py`, which launches ComfyUI as a child, runs the jobs, and shuts ComfyUI down.
The admission record then captures:
- device VRAM, RAM, the process-tree working set and private bytes
- commit charge/limit, pagefile use and pagefile growth
- PCIe gen/width at start, under load and at end
- wall time

The `comfy_run` report adds:
- startup time
- per job: wall time and ComfyUI execution time
- **per phase** (load / text_encode / denoise / vae_decode / output, from the websocket node events) and denoise step times
- timestamped ComfyUI log events (model loads, "loaded partially", OOM, tracebacks)
- output files and status

```powershell
. .\tools\windows\oc_env.ps1
$X = "$env:ONECREATIONS_DATA\experiments\2026-10-0X_ltx25-r1a"
uv run python tools\admission\monitor.py --label ltx25-r1a `
  --meta width=512 height=320 frames=49 fps=24 quant=int8-convrot sysmem=driver-default runtime=comfyui@<sha> `
         nodes=ComfyUI-LTXVideo@<sha> driver=591.74 comfy_report=$X\report.json `
  --notes "official 2.5 T2V single-stage distilled, INT8 ConvRot, enhancer off" -- `
  uv run python tools\admission\comfy_run.py --workflow workflows\ltx25\r1_t2v_api.json --repeat 2 `
    --seed "<node>/noise_seed=1000" --report $X\report.json --launch-log $X\comfy.log -- `
    <comfy python.exe> main.py --port 8188 --output-directory $X --temp-directory $env:ONECREATIONS_DATA\temp\comfy
```

`--repeat 2` runs one cold and one warm job, and the seed is incremented per job so ComfyUI cannot serve the warm run from cache. Add a third
job only after the variant is viable, or if repeatability needs it. **After a failure,** read the telemetry first (OOM, `loaded partially`,
commit near limit, paging, PCIe), then make **one** change justified by that bottleneck, and retry under a new label. Further variants need evidence.

Then open `admission_records/records.jsonl`, set `"outcome"` (`pass` / `partial` / `fail`) with a one-line reason,
and add a row to the results table below. Keep failed rungs; they are evidence.

## Pass criteria (proposed in v1 §18 — targets, not facts)

- Completes the controlled graph repeatedly without OOM (sysmem fallback **disabled**, so OOM is visible).
- Peak observed device VRAM ≤ 10.5–11 GB (monitor flags > 11,000 MB).
- **No sustained paging during denoise/decode** (monitor flags pagefile growth > 1 GB; inspect the CSV — a spike during load is acceptable, a plateau during steps is not).
- 49-frame controlled preview ≤ 30 min end-to-end (initial usability target).
- Action survives well enough to pass a human review of the output.
- Three consecutive jobs from a clean launch succeed; an intentionally oversized request fails cleanly and the next job still runs.

Outcome per model (ADR-0001 D3): **A admitted**, **B preview-only** (reliable but slow/small), **C not admitted**.

## Ladder — LTX-2.5 22B distilled (primary candidate)

Assets (official 2.5 Comfy route, v1 §18 — the INT8 ConvRot files are Comfy-specific):
`ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors`, `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors`,
`ltx-2.5-video-vae-conv-bf16.safetensors`, and the Union adapter named in the official
`example_workflows/2.5/LTX-2.5_ICLoRA_Union_Control_Distilled.json` (record its hash; inspect it with
`tools/inspect_safetensors.py --lora-summary` and paste the rank/module summary into the registry).

32 GB RAM specifics (arithmetic, not prediction): transformer ≈ 22 GB + encoder ≈ 12 GB > 32 GB, so they must never be
resident together. Sequence: encode text/refs → **unload encoder** → denoise with block/model offload → **unload transformer**
→ tiled VAE decode → save. Try ComfyUI's memory flags (`--lowvram`, `--reserve-vram`, `--disable-smart-memory`, cache options —
confirm names with `python main.py --help` at the pinned commit). Each flag combination is its own labelled run.

| Rung | Setting (proposed) | Notes |
|---|---|---|
| 1 | T2V smoke, 512×320, 49 frames, batch 1, distilled schedule | Cold load + warm run timed separately |
| 2 | Same + first frame + official **depth** Union control | The graph we actually need |
| 3 | Rung 2 on three scenes: orbit, fast near pass, two-character motion | Use M2 diagnostic/V0 renders as controls |
| 4 | 576×320 or 640×384, 73–97 frames | Only if 1–3 are stable |
| 5 | 121 frames (~5 s @ 24 fps); larger resolution tested separately | |
| 6 | Repeat best setting ×3 from clean launch; oversized request → recovery | Reliability |

If rungs fail: reduce frames/resolution/reference length → verify offload & tiled decode → try **one** alternative runtime
(e.g. Wan2GP if it supports LTX-2.5 at that time, or the official LTX pipeline's own low-memory path) → stop.
INT4/GGUF variants are a *separate* later experiment, not a substitute result.

## Ladder — FLUX.2-klein-4B (keyframes; distilled for inference, base for T1)

| Rung | Setting |
|---|---|
| 1 | Text-to-image 1024×576, distilled 4B, default steps |
| 2 | Multi-reference edit with 2–3 approved character renders |
| 3 | Same with FP8/quantized transformer and/or CPU offload if rung 1–2 exceed 11 GB (published full pipeline ≈ 13 GB) |
| 4 | 20 consecutive images (stability) |

## Ladder — Wan2.1-VACE-1.3B (local small-model experiment)

| Rung | Setting |
|---|---|
| 1 | 480p (832×480), 49 frames, depth-control video + reference image |
| 2 | Mask/inpaint task: protect foreground, regenerate background |
| 3 | 81 frames |
| 4 | ×3 consecutive + oversized-request recovery |

## Results table (fill in; newest first)

| Date | Model | Rung | Settings | Peak VRAM (MB) | Peak RAM (MB) | Pagefile growth (MB) | Cold / warm / e2e | Outcome | Record |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-03 | LTX-2.5 22B distilled INT8 ConvRot + Union IC-LoRA | M2-C (authored camera move) | M2-A graph and prompt (verbatim, no camera words); M2-A temple + static rigid proxy; **one authored camera move** (24° orbit + 7.5→6.0 m push-in, raised 3.6→3.3 m, fixed 35 mm); 512×320×49; rules pre-registered; 1 generation | 11,949 | 30,429 (min avail 2,080; commit 76.2 %) | 50 (peak use 142) | 32.4 s / — / startup 7.1 s (warm cache) | **pass**: three static landmarks (8.6/10.9/15.6 m) follow their trajectories (cos ≥ 0.994, 0.90× magnitude, ≤ 11.8 px), parallax ratios within 0.6 %, framing within 7.7 px, monotone, no jumps; generated move ≈ 0.9× the authored one | `ltx25-m2c-camera` |
| 2026-10-03 | LTX-2.5 22B distilled INT8 ConvRot + Union IC-LoRA | M2-B @ 768×448 (same-shot resolution comparison) | the original-speed M2-B strike with **only the output resolution changed** (512×320 → 768×448; guide grid 8×5 → 12×7 cells of 64 px); rules pre-registered; 1 generation | 11,949 | 30,451 (min avail 2,058; commit 75.5 %) | 8 (peak use 162) | 37.7 s / — / startup 7.1 s (warm cache); median step 1.00 s vs 0.594 s at 512 | **admitted; NO MATERIAL IMPROVEMENT** for the fast weapon: fast-region retention worst 0.117 (512: 0.009), median 0.568 (0.570), f25 still a ghost, shaft still missing; timing 0/0 frames, body within 1.9 px; static detail sharper; M2-B shot class still partial | `ltx25-m2b-strike-768` |
| 2026-10-03 | LTX-2.5 22B distilled INT8 ConvRot + Union IC-LoRA | M2-B retry (the one evidence-driven retry) | as M2-B with **one change**: the strike stretched ×1.5 in time (6 → 9 frames; GT peak head speed 80 → 64 px/frame) | 11,501 | 30,459 (min avail 2,050; commit 75.0 %) | 103 (peak use 171) | 31.7 s / — / startup 7.1 s (warm cache) | **partial**: metric PASS (apex/contact +1/0 frames, excursion 102 %, body within 2.1 px); the smear follows the new fast frames (f26–f29, 43–64 px/frame), worst frame less severe (gold area 23 % vs 0.9 %); no further retries | `ltx25-m2b-strike-retry` |
| 2026-10-03 | LTX-2.5 22B distilled INT8 ConvRot + Union IC-LoRA | M2-B (articulated strike) | M2-A graph and prompt unchanged; same temple, static camera; rigged proxy, **root fixed**, one mace strike (guard → wind-up → apex f24 → strike → contact f30 → hold → recovery); 512×320×49; 1 generation | 11,495 | 30,445 (min avail 2,064; commit 74.4 %) | 39 (peak use 69) | 32.6 s / — / startup 29.0 s | **partial**: metric PASS (apex/contact 0/0 frames off GT, excursion 102 %, body within 2.6 px, arm visibly changes pose through every phase) but the weapon is ghosted/smeared and the shaft unresolved in the 3 fastest frames (76–87 px/frame) | `ltx25-m2b-strike` |
| 2026-10-02 | LTX-2.5 22B distilled INT8 ConvRot + Union IC-LoRA | M2-A (representative temple shot) | R2D graph with a neutral prompt; procedural temple courtyard, static camera; **whole-body rigid translation** of a humanoid-shaped proxy, L→R while approaching; 512×320×49; 1 generation | 11,949 | 30,444 (min avail 2,065; commit 74.6 %) | 19 (peak use 131) | 32.3 s / — / startup 7.2 s (warm cache) | **pass**: 98.5 % of travel, within 0–2.8 px of the reference-tracked path; area ×1.35 vs ×1.39; structures stable; small occluded secondary re-emerges degraded (caveat) | `ltx25-m2a-temple` |
| 2026-10-02 | LTX-2.5 22B distilled INT8 ConvRot + Union IC-LoRA | R2D (control diagnostic) | R2 graph with a neutral prompt; static camera, red box L→R + blue ball toward camera; corrected depth control (min–max, lossless); 512×320×49; 1 generation | 11,943 | 30,385 (min avail 2,124; commit 74.8 %) | 8 (peak use 126) | 33.1 s / — / startup 6.6 s (warm cache) | **pass**: box centroid within 0.2–2.9 px of GT, 99.9 % of travel; ball area ×6.20 vs ×6.42 | `ltx25-r2d-control-diagnostic` |
| 2026-10-02 | LTX-2.5 22B distilled INT8 ConvRot + Union IC-LoRA | R2 | first frame + Blender depth Union control, stage 1, 512×320×49, 8 steps, ComfyUI defaults, driver-default sysmem | 11,949 | 30,501 (min avail 2,008; commit 75.4 %) | 63 (peak use 156) | 32.7 s / 8.9 s / startup 6.2 s (warm cache) | partial (owner): motion present but vague in playback, direction hard to read; keyframes track the depth control (frame-sheet check) | `ltx25-r2` |
| 2026-10-02 | LTX-2.5 22B distilled INT8 ConvRot | R1b | as R1a, **Prefer No Sysmem Fallback** for the ComfyUI interpreter only | 11,373 | 30,470 (min avail 2,039; commit 73.8 %) | 42 (peak use 93) | 31.1 s / 8.7 s / startup 23.4 s (warm cache) | pass: outputs byte-identical to R1a; no OOM without sysmem fallback | `ltx25-r1b` |
| 2026-10-02 | LTX-2.5 22B distilled INT8 ConvRot | R1a | T2V video-only, 512×320×49, 8 steps, ComfyUI defaults (DynamicVRAM, pinned 13 GB, async offload), driver-default sysmem, cold restart | 11,943 | 30,455 (min avail 2,055; commit 74.3 %) | 69 (peak use 69) | 31.1 s / 7.8 s / startup 29.0 s (cold) | pass (owner): coherent, on-prompt; faces unclear at this envelope | `ltx25-r1a` |

Peak VRAM is device-wide `nvidia-smi` and goes above the 11,000 MB proposed target because ComfyUI's DynamicVRAM fills the card on purpose.
R1b shows that this does not depend on CUDA sysmem fallback.

Under load the link was Gen4 x16, except for about 1–5 low-power seconds at gen2 x16 while weights stream in at the start of denoising.
The width stayed x16 throughout.

Per-phase timings for each run are in `admission_records/2026-10-02_<label>_comfy_report.json`.

**Running a controlled shot (from M2-A on):** use `tools\windows\run_admission.ps1`.
- It takes `-Label`, `-Workflow` and `-InputDir` (which must hold `first_frame.png`, `depth_control.mp4` and its `.json` sidecar), plus `-Meta`.
- It records the input hashes as run metadata.
- Cache keys come from `tools/admission/experiment_keys.py`.
- The pre-LTX gate and the comparison come from `tools/admission/control_diagnostic.py --spec <scene spec>`.
- Moving-camera shots (M2-C on): the scene spec's `tracking` adds static landmarks with `trajectory` checks, a shot-level `parallax` check, the camera contract (exported vs authored `CameraMotion`) and clearance (exact Blender distances + `camera.retarget.clearance_report`); generated viewpoint evidence is image-space only.
- Same-shot comparisons across output sizes: `tools/admission/resolution_compare.py` reports the guide grid, the weapon's size and motion in px and in guide cells, and the per-frame generated/reference retention (M2-B 768×448, 2026-10-03).
- From M2-B on, `first_frame.png` and `reference_preview.mp4` come from `integrations/blender/render_reference.py` (Cycles OptiX, 64 spp, seed 0, lossless preview, sidecar with hashes).

## G2 exit

Each of LTX-2.5, FLUX.2-klein-4B and Wan2.1-VACE-1.3B has an outcome A/B/C recorded here, in `records.jsonl`, and in
`model_registry/models.yaml` (`admission.status`). If LTX-2.5 is **C**, stop and raise open question 1 in `STATUS.md`
with the owner before anything else that depends on it.
