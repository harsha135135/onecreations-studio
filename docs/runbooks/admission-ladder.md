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
| — | — | — | — | — | — | — | — | — | — |

## G2 exit

Each of LTX-2.5, FLUX.2-klein-4B and Wan2.1-VACE-1.3B has an outcome A/B/C recorded here, in `records.jsonl`, and in
`model_registry/models.yaml` (`admission.status`). If LTX-2.5 is **C**, stop and raise open question 1 in `STATUS.md`
with the owner before anything else that depends on it.
