# Runbook M1 — Windows desktop setup (gate G0)

Target: Windows 11 · RTX 4070 12 GB · i7-14700K (UHD 770 iGPU) · 32 GB RAM. Rationale: ADR-0001 D6.
Everything here is local and free. Tick the boxes in `STATUS.md` when done.

## 1. Hardware and OS settings

1. **Display on the iGPU.** In BIOS/UEFI enable the integrated graphics (often "iGPU Multi-Monitor" / "Primary Display: IGFX"). Plug the monitor into the **motherboard** video output. After boot, `nvidia-smi` should show `display_active = Disabled` and only a few hundred MB used at idle.
   - Windows *Settings → System → Display → Graphics* lets you pin Blender/ComfyUI to the RTX 4070 as "High performance" while the desktop stays on the iGPU.
2. **CUDA sysmem fallback off.** NVIDIA Control Panel → *Manage 3D settings* → *Program settings* → add each venv's `python.exe` (and Blender) → *CUDA – Sysmem Fallback Policy* → **Prefer No Sysmem Fallback**. Without this, VRAM overflow silently spills into shared RAM and runs far slower instead of raising OOM, which corrupts admission measurements.
3. **Pagefile.** *System → Advanced system settings → Performance → Advanced → Virtual memory*: fixed size on the fastest NVMe, e.g. initial = max = 48–64 GB. It's a safety net for *loading* big checkpoints on 32 GB RAM; sustained paging during denoise/training steps counts as a failed rung.
4. **Power:** "Best performance" power mode; disable USB selective suspend for long runs.
5. **Windows Update:** before any multi-hour run, *Pause updates* (or set active hours) so the machine doesn't reboot mid-run.
6. **Defender:** add exclusions for the data root and the venv folders (real-time scanning of multi-GB `.safetensors` reads slows loading badly).

> **Owner decision 2026-10-02 (M1):** baseline first, tune later. Items 2, 3 and 6 were **not** applied in M1. The pagefile stays
> system-managed, there are no Defender exclusions, and the sysmem-fallback policy has not been changed globally. Apply one only when a
> measured admission run shows the need: sysmem fallback per executable/profile, never global; Defender as the
> narrowest data/cache path. Item 1 (iGPU display) was applied, with idle VRAM measured before and after.

## 2. Data root (outside Git, outside OneDrive)

This desktop uses `G:\onecreations\` (owner-approved 2026-10-02, **temporary**). There is no D: drive: a single 1 TB NVMe is
split into C:, F: and G:, and G: had about 280 GB free at setup. Do storage planning before M2/M3. Change the path here and in `STATUS.md` if it moves:

```
G:\onecreations\
  models\      # checkpoints, by family (ltx\, flux2\, wan\) — hashes go in model_registry/models.yaml
  datasets\    # rendered training/eval data + manifests
  caches\      # latents / text embeddings, one folder per (model, encoder, VAE) hash
  renders\     # Blender outputs, control passes
  envs\        # optional: venvs for upstream tools (ComfyUI, trainers)
  upstream\    # pinned clones of ComfyUI, ComfyUI-LTXVideo, trainers
```

## 3. Base tools

Install (winget or official installers): **Git**, **uv** (`winget install astral-sh.uv`), latest **NVIDIA Studio/Game Ready driver**, **Blender 4.5 LTS** (pinned; don't auto-update), **FFmpeg**, **7-Zip**. Optional: VS Code.

The CUDA toolkit is **not** needed for prebuilt PyTorch wheels; install it only if a build step demands it.

## 4. This repo

```powershell
cd C:\Users\ADMIN\documents\developer\llm   # this desktop's code folder (not OneDrive-synced)
git clone https://github.com/harsha135135/onecreations-studio.git
cd onecreations-studio
uv sync
uv run pytest -q                       # includes 11 headless-Blender tests when Blender 4.5 is found
uv run onecreations blender info       # should report the pinned 4.5 series
powershell -ExecutionPolicy Bypass -File tools\windows\check_env.ps1 -DataRoot G:\onecreations
```

If Blender isn't in the default location (`C:\Program Files\Blender Foundation\Blender 4.5\blender.exe`), set
`$env:ONECREATIONS_BLENDER = "X:\path\to\blender.exe"` before running the tests. The Blender tests check the export
contract against Blender's own projection and the diagnostic scene's known geometry; compare the numbers with the
Mac measurements in `docs/contracts.md` and note any difference in `STATUS.md`.

`git config user.name "Harshavardhan M"` and the user's email must be set on the desktop (no AI co-author lines; see `CLAUDE.md`).

## 5. Separate environments per backend

One venv per upstream tool, never one global environment (v1 §19). Pin every upstream clone to a commit and write the SHA into `model_registry/models.yaml` → `runtimes:`.

| Env | Purpose | Notes |
|---|---|---|
| `comfyui` | LTX-2.5, FLUX.2-klein, Wan VACE inference graphs | ComfyUI (manual install or portable build) + ComfyUI-LTXVideo nodes at pinned commits. Use the PyTorch/CUDA build that ComfyUI's README recommends at that commit. |
| `flux-train` | T1 FLUX.2-klein-base-4B LoRA | Trainer chosen in `docs/runbooks/local-training.md` |
| `wan-train` | Wan2.1-VACE-1.3B LoRA (and TI2V-5B if justified) | musubi-tuner or DiffSynth-Studio, whichever supports VACE-1.3B LoRA at the pinned commit |
| `ltx-prep` | LTX-2 trainer *preprocessing and config validation only* (no 22B training locally) | Same commit that will run on the H100 |

Rules: PyTorch SDPA attention first; no flash-attn / SageAttention / triton-windows / `torch.compile` until the baseline passes and the speed-up is measured (record it as its own admission rung).

Check each env's torch install:

```powershell
powershell -ExecutionPolicy Bypass -File tools\windows\check_env.ps1 -TorchPython G:\onecreations\envs\comfyui\.venv\Scripts\python.exe
```

## 6. G0 exit

- `check_env.ps1` exits 0 with no FAIL; WARNs reviewed.
- Idle VRAM ≈ a few hundred MB with display on the iGPU.
- Sysmem-fallback policy: deferred to the M3 admission phase, per executable, after baseline behaviour is recorded (see the owner decision in §1). No model env exists at G0.
- `uv run pytest -q` passes on the desktop, **including the Blender tests** (not skipped).

Record the `check_env.ps1` output summary in the `STATUS.md` session log.
