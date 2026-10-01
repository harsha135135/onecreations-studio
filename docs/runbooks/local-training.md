# Runbook M6 — Local training on the RTX 4070 (gate G4)

Precondition: **G3** — the T0 benchmark named a repeatable, learnable defect for the task being trained
(or showed none, in which case skip training). Strategy: ADR-0001 D2. Experiment cards live in `training/`.

All settings below are **proposed starting points**, not verified memory figures. Confirm each one with the
monitor and record it, exactly like an inference rung.

## Shared discipline (v1 §16)

- Pre-cache text embeddings and latents with the exact encoder/VAE revision; cache folder name includes those hashes.
  Never let the text encoder or VAE stay resident during training steps.
- Batch 1 + gradient accumulation, gradient checkpointing, bf16 LoRA weights, 8-bit AdamW where the trainer supports it.
- Grouped splits by scene / asset / choreography / camera family (v1 §14). Hold-out families never enter training.
- Checkpoint every N steps; test **resume** once before any long run.
- Stop on held-out acceptance, not training loss. All checkpoints and all seeds reported.
- Training admission ladder for each run: **load → 1 forward/backward → 50-step timing → save → reload → run the
  deployment inference graph with the LoRA → compare against no-LoRA**. Wrap with `tools/admission/monitor.py`.
- Stop rule: if measured step time means the pilot can't finish one epoch within its cap, reduce resolution/frames or stop.

## T1 — FLUX.2-klein-base-4B image LoRA (local first)

Card: `training/image_lora/experiment-card-t1-flux2-klein.yaml`.

- Trainer: whichever of (a) the BFL/diffusers FLUX.2-klein LoRA recipe referenced in v1 §16, (b) ai-toolkit, (c) musubi-tuner
  supports FLUX.2-klein **base 4B** at a pinned commit and runs natively on Windows. Pick one; record the SHA.
- Start: 512 px buckets, rank 16, FP8 (or NF4) frozen base, cached embeddings/latents, grad checkpointing,
  batch 1 × grad-accum 4. Move to 768/1024 only with ≥ 1 GB VRAM headroom at 512.
- Deploy/validate on the **distilled 4B** inference route (base→distilled, per the BFL guide).
- Cap: **≤ 12 local GPU-hours** including caching and validation.
- Cloud fallback (ADR-0001 D4): RTX 4090 ≤ 4 h (Gate A) only if local T1 OOMs at 512 px or is impractically slow,
  after `ledger.py check` and owner approval.

## T2-small — Wan2.1-VACE-1.3B LoRA (local experiment + rehearsal)

Card: `training/video_adapter/experiment-card-t2s-wan-vace-1.3b.yaml`.

Why: it is the cheapest way to prove the full video-adapter loop (dataset → caches → train → reload → controlled
inference → held-out eval) on our own data before renting an H100. Its weights do **not** transfer to LTX-2.5.

- Trainer: musubi-tuner or DiffSynth-Studio — whichever supports **VACE-1.3B LoRA with control/reference inputs** at a pinned
  commit on Windows. If neither supports VACE conditioning, train a plain Wan2.1-T2V-1.3B LoRA on the same targets and
  label it as a rehearsal only.
- Start: bf16 base, rank 16–32 on attention projections, cached umT5 embeddings (encode once, then unload — the encoder is large)
  and cached VAE latents, 320×576 → 480×832, 33 → 49 frames, depth control first.
- Data: the 200-clip diagnostic set (v1 §14), grouped splits.
- Caps: pilot **≤ 24 h**, full **≤ 72 h** of local GPU time.

## LTX-2.5 preparation (local; training itself happens on the H100)

Goal: make the paid H100 hours do only what needs 80 GB.

1. Clone the official LTX-2 repo; pin a commit; create the `ltx-prep` env; read `packages/ltx-trainer` docs (training modes,
   `v2v_ic_lora.yaml`, low-VRAM config) at that commit.
2. Download the Union adapter used by the official 2.5 workflow. Run
   `uv run python tools/inspect_safetensors.py <union>.safetensors --lora-summary --json > model_registry/union_adapter_summary.json`.
   This gives its real rank and target modules — don't assume the example config's rank.
3. Check whether the pinned trainer can **load/resume** that adapter (module names match what the trainer creates). If names
   don't match, document it: the continuation path may be blocked before any money is spent (v1 §16: then stop T2 or open a new,
   separately approved experiment).
4. Build the IC-LoRA dataset: paired control (depth) + target RGB clips, 49 frames, manifests, grouped splits, rights records.
   Validate with the M2 diagnostic checks.
5. Try the trainer's **latent and text-embedding preprocessing locally**. If it fits on 12 GB / 32 GB (VAE encode with tiling,
   encoder possibly quantized if the trainer supports it), keep the caches and upload them — that saves H100 hours. If it
   doesn't fit, do it on the H100 and count it against the admission hours. Caches must come from the exact checkpoint
   revisions the H100 job will use.
6. Write the trainer-native config derived from the pinned upstream example, plus a launch script that: sets a wall-clock
   limit, checkpoints every N steps, runs a held-out validation at the end, and copies outputs back.
7. Dry-run on the 4070 anything that doesn't need the 22B model (data loader, config parsing, small validation scripts).

## G4 exit

- T1 and/or VACE-1.3B: full loop train → save → reload → deployment graph → held-out comparison completed and recorded.
- LTX: adapter inspected, trainer resume compatibility assessed, dataset + manifests + (ideally) caches ready, config + launch
  script ready.
- LTX-2.5 admission outcome **A or B**. If **C**: no LTX training spend without the owner's decision (ADR-0001 D3).
