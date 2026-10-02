# Post-update verification and R1 setup — 2026-10-02 (Windows desktop)

Every figure is **measured** on this desktop unless labelled otherwise. This record continues `2026-10-02-desktop-m1.md`.

## Windows Update (owner: finish the pending update; preserve the baselined drivers)

- **Pending before the update:** the 2026-09 cumulative update KB5129195 (→ 26200.9457), .NET KB5126052, MSRT, the Defender/security platform, and 6 driver updates.
- **Drivers Windows would install automatically** (`DeploymentAction=1`): NVIDIA 32.0.15.9186 and Intel RST VMD 20.2.6.1025 (the boot NVMe's controller). Both were hidden through the `Microsoft.Update.Session` COM API.
- **Optional drivers** (`DeploymentAction=4`): Intel Display 31.0.101.3302 (older than installed), Intel Bluetooth, Intel Wi-Fi, and NVIDIA 32.0.16.1088. These were left unselected.
- **Result: the hide held for Intel RST, which is still 20.1.0.1015 and still hidden. It did _not_ hold for NVIDIA.**
  - Windows Update installed **NVIDIA 32.0.15.9186 (591.86) at 11:34–11:35** anyway. Event log: WindowsUpdateClient ids 43 and 19.
  - The update had already been downloaded and queued, and the Windows 11 update orchestrator did not honour the legacy hidden flag.
  - An unlisted *Microsoft AudioProcessingObject* driver was also installed automatically at 11:49.
  - The 591.74 package is still in the driver store (`oem7.inf`).
- **Owner decision:** accept **591.86 as the new pinned driver** and re-baseline. Lesson: hiding is not reliable for an update that is already queued. Pause updates *before* hiding, or use the WU driver-exclusion policy (owner's call).
- **After the 12:04 reboot:**
  - The OS is **26200.9457**, and no reboot is pending.
  - Drivers: NVIDIA 32.0.15.9186, Intel UHD 32.0.101.7088, Intel RST 20.1.0.1015.
  - Still pending: the security platform update, MSRT, and the optional drivers. **Updates must be paused before the runs.**

## Re-baseline on driver 591.86 (display on the UHD 770)

| | M1, driver 591.74 | Post-update, driver 591.86 |
|---|---|---|
| Idle 4070 VRAM (30 × 1 s) | 129 MiB | **0 MiB** (min = median = max) |
| Idle power | 3.0 W | 2.7–3.0 W |
| VRAM during the same OptiX render | 1288 MiB | 1159 MiB |
| PCIe under load | Gen4 x16 (273 samples) | **Gen4 x16** (128 samples, from the new monitor) |
| OptiX render time (1080p, 4096 spp) | 71.6 s | 72.4 s |
| `check_env.ps1` | 0 FAIL / 3 WARN | 0 FAIL / 3 WARN (same accepted WARNs), plus a torch PASS in the ComfyUI env |
| `pytest` | 107 passed | **117 passed** (new admission tooling tests) |

The 129 → 0 MiB idle difference is what the driver *reports*; the display was on the iGPU in both cases.

**Monitor validation** (`monitor.py` wrapping the OptiX render):
- 135 samples at 0.5 s
- `pcie_start` gen1 x16, under load **gen4 x16 ×128**, `pcie_end` gen4 x16, no flags
- commit 9.2 GB → peak 11.1 GB of a 60.2 GB limit (18.5 %)
- pagefile use 0 MB
- process-tree private bytes 1.8 GB

## Smart App Control (owner action)

After the reboot, ComfyUI failed at import:

```
ImportError: DLL load failed while importing _core: An Application Control policy has blocked this file.
```

- **What was blocked:** **Smart App Control** was enforcing (`VerifiedAndReputablePolicyState=1`) and blocked PyAV's unsigned `av.libs\libstdc++-6-*.dll` (CodeIntegrity events 3033/3077/3118). PyAV is imported unconditionally by ComfyUI core.
- **The odd part:** the same import worked at about 11:45, before the reboot, with no block events. SAC was already enforcing then: it blocked a `.winmd` in Downloads at 09:00. Whether the update or a changed cloud reputation verdict caused the new block is **not identified**.
- **Scope:** every other native module in the ComfyUI env imported fine, including torch, comfy_kitchen, comfy_aimdo and OpenImageIO.
- **Owner decision:** the owner turned **Smart App Control off** in Windows Security. The state is now 0, and PyAV 19.0.0 imports. This is a system-wide security-posture change made by the owner. On some Windows builds SAC cannot be re-enabled without a reset.

## ComfyUI runtime (M3 setup)

| Item | Value |
|---|---|
| ComfyUI | v0.38.0 = `6b747c0428c343e1417219641db93a4fb7cb69ae`, in `G:\onecreations\comfy\ComfyUI` |
| ComfyUI-LTXVideo | `3bf3ca62595f1764c47d01c35c8e5dfe47e1a88f` (2026-10-01) |
| Python | **dedicated** uv-managed CPython 3.13.16 at `G:\onecreations\comfy\python\cpython-3.13.16-windows-x86_64-none\python.exe` (the CUDA process; a per-exe NVIDIA profile targets this exe) |
| torch | 2.14.1+cu130 (CUDA 13.0), torchvision 0.29.1, torchaudio 2.11.0; bf16 and SDPA available on the RTX 4070 |
| Key packages | comfy-kitchen 0.2.36 (cuda backend; triton unavailable), comfy-aimdo 0.5.5, av 19.0.0, transformers 5.18.0, safetensors 0.8.0 |
| Defaults reported at startup | `NORMAL_VRAM`, cudaMallocAsync, async weight offload (2 streams), **pinned memory 13003 MB**, **DynamicVRAM enabled** (comfy-aimdo, NVML pressure, WDDM adapter match), pytorch attention |
| Model paths | `G:\onecreations\comfy\extra_model_paths.yaml` → `G:\onecreations\models\ltx\…` |
| `comfy_run` against real ComfyUI | startup 6.6 s with a warm file cache (30.9 s on the first cold start). A no-model graph produces an h264 mp4 at 512×320 / 24 fps. An identical second job is served fully from cache, which is why R1 offsets the seed. |

**Install footprint:** about 4.5 GB in `comfy\`, plus a 4.2 GB uv wheel cache in `temp\`, all on G:. The uv cache on C: stayed at 0.05 GB.

## R1 download (staged; owner rule: only what the minimal T2V graph strictly needs)

The official `LTX-2.5_T2V_I2V_Single_Stage_Distilled` graph loads 5 models: bf16 transformer, bf16 Gemma encoder, Gemma-E2B enhancer, video VAE, and audio VAE. In the official graph, the audio VAE feeds `LTXVEmptyLatentAudio` and `LTXVAudioVAEDecode`.

ComfyUI core accepts a **video-only** latent: `av_model.py` substitutes a zero-length audio tensor, and `recombine_audio_and_video_latents` then returns video only. So the minimal R1 graph needs no audio VAE.

The Gemma tokenizer is embedded in the encoder file (`spiece_model`). The R1 download from `Lightricks/LTX-2.5` at revision `5e6e71018ee1756ed329b697a7b4aedc934dfce9` is:

| File | Published size | Published LFS SHA-256 |
|---|---|---|
| `diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` | 21.50 GB | `c4279eeff115cbeaca494bd2183e7d768c38fe85a184dc6afbb7159157c44334` |
| `text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | 15.37 GB | `6ce688a0aa98a5fa36a9f1e6c3f42152a498cc2b53ee8c15674c64244f91487f` |
| `vae/ltx-2.5-video-vae-bf16.safetensors` | 1.47 GB | `847e14ca7f3355debca0cea4eaa24ac0fbcdf0061da054ac89ca638a869ddba3` |

These total 38.35 GB. Nothing else was downloaded: no audio VAE, upscaler, bf16/dev/NVFP4, E2B or Union files.

The download ran at about 12 MB/s of network throughput, roughly 55 min. Licence snapshots are in `model_registry/licenses/`:
- **LTX-2.x Community License** (dated 2026-08-11; `Lightricks/LTX-2@2d6e71c8:LICENSE-2_x`; SHA-256 `be75acae…`). It applies to LTX-2.5.
- the model card at `5e6e7101`.
