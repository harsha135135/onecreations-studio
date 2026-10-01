# ADR-0001 — Hardware and compute strategy: 4070-first, H100 only after admission

- **Status:** Accepted — 2 October 2026
- **Owner:** Harshavardhan M
- **Supersedes, where they conflict:** §1, §5, §16, §17, §18, §19, §20, §30 of `docs/research/2026-10-01-decision-v1.md`
- **Does not change:** the architecture, shot/asset/camera/event contracts, dataset rights policy, evaluation design or "what not to build" list of v1.

## Context

| Item | Value |
|---|---|
| Training/inference desktop | Windows 11, **RTX 4070 12 GB**, **i7-14700K** (has UHD 770 iGPU), **32 GB RAM** |
| Development machine (now) | macOS laptop: docs, contracts, tooling, tests. No CUDA here. |
| External compute ceiling | **₹15,000 total** for all external compute (GPU rental, cloud storage/egress, any paid comparison). User's working range ₹10,000–15,000. |

v1 planned the desktop around 64 GB RAM. This machine has 32 GB. v1 also left open what "local" means for training. This ADR settles both.

## Decisions

### D1 — Primary model is chosen by final quality and controllability, not by what fits the 4070

- **LTX-2.5 22B distilled + documented Union IC-LoRA control graph stays the primary candidate**, as v1 recommends, because of its workflow coverage (references, depth/pose/edge control, distilled few-step inference, IC-LoRA training path).
- The primary is **confirmed or replaced only by the T0 benchmark** (v1 §21: action/contact, camera/layout, identity, VFX readability, temporal stability, artist time). Challengers, in order: Wan2.1-VACE-14B, Bernini-R, Wan2.2-TI2V-5B.
- **Wan2.1-VACE-1.3B is a local small-model experiment, not the primary.** It earns its place because it is cheap to run and train on the 4070, so it can debug the whole data → cache → train → reload → evaluate loop before any money is spent. A VACE-1.3B adapter does **not** transfer to LTX-2.5, and VACE-1.3B becomes primary only if it wins the benchmark on quality, which is unlikely.

### D2 — 4070-first → H100 only after admission

Everything that is realistically feasible locally is developed, debugged and, where possible, trained locally. Cloud GPUs are rented only for high-value training that cannot reasonably fit locally, and only after local gates pass.

| Work item | Where | Notes |
|---|---|---|
| Blender scene, rigs, choreography, camera library, VFX events, control export | 4070 / CPU | Core product; no cloud |
| Diagnostic scene (cube/occluder/known camera) and channel-convention tests | 4070 / CPU | v1 §15; must pass before any dataset render |
| Dataset rendering, captions, manifests, grouped splits, rights records | 4070 / CPU | All of it locally |
| **LTX-2.5 inference admission ladder** (quantized + offloaded) | **4070, measured** | D3: run first, never assume failure |
| FLUX.2-klein-4B and Wan2.1-VACE-1.3B inference admission | 4070 | Same ladder discipline |
| T0 pretrained conditioning baseline on the benchmark | 4070 | Uses whatever passed admission |
| **T1** FLUX.2-klein-base-4B image LoRA | **4070 first** | RTX 4090 rental only as a fallback if local T1 OOMs or is impractically slow |
| **T2-small** Wan2.1-VACE-1.3B LoRA | 4070 | Pipeline rehearsal + small-model result |
| LTX trainer: pin commit, build env recipe, validate configs, inspect Union adapter rank/modules from safetensors header | Mac/4070 | No 22B load needed (`tools/inspect_safetensors.py`) |
| LTX latent + text-embedding precompute | 4070 **if** the pinned trainer's preprocessing fits; else on H100 (counted) | Caches must match the exact VAE/encoder revision used in the cloud |
| **T2** LTX-2.5 Union IC-LoRA continuation (or narrow IC-LoRA) | **H100 PCIe 80 GB** | Only after Gate G4 (below). H200 only if 80 GB OOM is measured |
| Evaluating trained LTX adapter | 4070 if LTX admitted locally; else see D3 outcome C | |

### D3 — LTX-2.5 inference on 32 GB RAM is an open question; measure it

Do not assume it fails. Run v1 §18's ladder with the official Comfy INT8 ConvRot assets and record each rung (`docs/runbooks/admission-ladder.md`).

Known risk to watch, stated as arithmetic, not prediction: the INT8 transformer (~22 GB) and the INT8 Gemma encoder (~12 GB) together exceed 32 GB, so they must never be resident together; encode → unload → denoise → unload → tiled decode. Mmap/streaming from NVMe may make it work slowly. Sustained pagefile thrashing during denoise counts as a failed rung.

| Outcome | Meaning | Consequence |
|---|---|---|
| **A — Admitted** | Controlled graph completes repeatedly within v1 §18 pass criteria | LTX-2.5 is deployable locally. T2 eligible. |
| **B — Preview-only** | Works at reduced frames/resolution or > 30 min per 49-frame preview, but reliable | Still deployable for offline work; T2 eligible if the benchmark shows a learnable defect. Record the envelope. |
| **C — Not admitted** | OOM/thrash/unreliable after the ladder + one alternative runtime | LTX cannot be the *local* deployment target. **Stop and ask the owner** before any LTX cloud spend. Options: (i) a ≤ 2 h H100 cloud T0 comparison (≤ ₹710) to see whether LTX quality justifies cloud inference or a RAM/GPU upgrade; (ii) promote the best admitted challenger; (iii) Blender path only. v1's rule stands: OneCreations does not silently become a cloud-inference product. |

### D4 — Budget: ₹15,000 hard ceiling, gated

Planning rates and allocations are v1 §17's (₹100/US$ assumption + 22% margin, Runpod list prices retrieved for v1). Re-check live prices before every launch.

| Line | Gate A (cumulative ≤ ₹5,000) | Gate B (cumulative ≤ ₹15,000) |
|---|---:|---:|
| RTX 4090 — **T1 fallback only** (local first) | ≤ 4 h = ₹380 | ≤ 6 h = ₹570 |
| H100 PCIe — T2 LTX adapter | ≤ 8 h = ₹2,840 (2 admission/caching + 4 pilot + 2 validation/export) | ≤ 32 h = ₹11,360 (2 + 10 first run + 10 continuation/ablation + 8 validation + 2 export/recovery) |
| Storage / transfer | ₹500 | ₹1,000 |
| Reserve (unspent unless approved) | ₹1,280 | ₹2,070 |
| **Total** | **₹5,000** | **₹15,000** |

Rules:
- Every rental is logged in `budget/ledger.csv` and pre-checked with `tools/budget/ledger.py check` **before** launch. The ledger refuses anything that would cross the active gate.
- **Gate B unlock requires the owner's explicit approval** after a Gate A pilot shows held-out improvement over the pretrained conditioned graph. Recorded in `budget/policy.json`.
- H200 (₹565/h) or A100 (₹195/h) may replace H100 hours only on measured evidence (80 GB OOM, or better cost per useful step). Charged against the same H100 line.
- Every job: wall-clock auto-stop, checkpoints, stop the GPU immediately after export, delete paid storage when done.
- Unspent money stays unspent. A weaker custom adapter is not a milestone.

### D5 — 32 GB RAM is the current hardware; plan around it, don't hide it

- RAM is not upgraded as part of this plan. v1's 64 GB recommendation remains the change that would most widen local options (LTX residency, Wan 14B/VACE-14B block swap).
- Local training excluded on 32 GB: anything 14B+ (Wan 14B, VACE-14B) and LTX-2.5 22B. Those go to H100 (LTX only, per D2) or are out of scope.
- Wan2.2-TI2V-5B (FP8 ≈ 5 GB weights) is a possible local experiment with block swap, only if T0 shows it is worth it.

### D6 — Windows environment (replaces v1 §19 for GPU work)

- **GPU work runs natively on Windows**, not in WSL2. WSL2 defaults to 50% of host RAM (16 GB here), which breaks offload/block swap. WSL is optional for CPU-only Linux tools.
- **Display on the iGPU** (monitor in the motherboard port, iGPU enabled in BIOS) so the 4070's 12 GB is all available.
- NVIDIA Control Panel → *CUDA – Sysmem Fallback Policy* → **Prefer No Sysmem Fallback** for each venv's `python.exe`, so VRAM overflow raises OOM instead of silently running much slower through shared memory.
- Pagefile: fixed size on the fastest NVMe (safety net for model *loading*). Sustained paging during steps = failed configuration.
- Separate `uv` venvs per backend (ComfyUI, FLUX training, Wan training). PyTorch SDPA attention; no flash-attn/triton/torch.compile until a baseline passes and the speed-up can be measured.
- Pause Windows Update during long runs; exclude model/data/cache folders from Defender real-time scanning and from OneDrive.
- One GPU-heavy job at a time.

### D7 — Cloud runs use the same code and data contract

The cloud run must only be a bigger GPU running what was already validated locally: same pinned trainer commit, same data manifests and split files, same caches (or the same precompute script), same experiment card. Anything new found in the cloud is a new experiment and goes back through local validation first.

## Gates (summary; details in `STATUS.md`)

| Gate | Pass condition | Unlocks |
|---|---|---|
| G0 | `tools/windows/check_env.ps1` clean; iGPU display; idle VRAM ≈ 0 | Everything |
| G1 | Diagnostic scene passes all channel-convention checks | Dataset rendering |
| G2 | Admission ladders recorded for LTX-2.5, FLUX.2-klein-4B, VACE-1.3B (outcome A/B/C each) | T0 |
| G3 | T0 benchmark done; primary confirmed; named, repeatable, learnable defect identified | Training |
| G4 | Local training rehearsal passes (T1 and/or VACE-1.3B: train → save → reload → deployment graph → held-out eval) **and** LTX dataset + caches + config validated locally **and** LTX outcome A or B | Gate A cloud spend (≤ ₹5,000) |
| G5 | H100 admission (≤ 2 h): load, 1 fwd/bwd, save, reload, target inference graph, compare to untouched adapter | H100 pilot |
| G6 | Pilot adapter beats the pretrained conditioned graph on held-out shots **and owner approves** | Gate B (≤ ₹15,000 total) |

## Consequences

- The product's core (Blender scene/action/camera/VFX/compositing) progresses regardless of any model outcome.
- Most iteration cost is local time and electricity, not rupees.
- If LTX is not admitted locally (outcome C), the LTX training budget is frozen until the owner decides.
