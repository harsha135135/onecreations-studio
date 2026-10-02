# R2D — LTX-2.5 Union-control diagnostic — 2026-10-02

**Question:** can LTX-2.5 clearly obey an intentionally obvious Blender-authored spatial and motion signal on this machine (RTX 4070 12 GB, 32 GB RAM)?

**Answer: yes. R2D = PASS** (one generation, no retry).

All figures are **measured**, single observation, unless labelled otherwise.

**Owner constraints for this session:**
- no hardware purchases; the current machine and storage are permanent
- storage efficiency is architectural
- control diagnostic only: no quality work, no 960×544, no upscaler, no training, no cloud, no new downloads
- one generation plus at most one evidence-driven retry

## 1. Depth-control input: what the official path expects vs. what we produced

**Sources inspected:**
- **Guide node:** the pinned `ComfyUI-LTXVideo@3bf3ca62` `iclora.py` (`LTXAddVideoICLoRAGuide.encode`/`execute`).
- **Official graph:** `example_workflows/2.5/LTX-2.5_ICLoRA_Union_Control_Distilled.json`.
  - Its depth branch runs `LoadVideoDepthAnythingModel (video_depth_anything_vits.pth)` → `VideoDepthAnythingProcess (518, 960, fp32)` → `VideoDepthAnythingOutput (gray)` → `ResizeImageMaskNode` ×2 → guide.
- **Depth preprocessor nodes:** `yuvraj108c/ComfyUI-Video-Depth-Anything@a0db08e6` `node.py`. This node pack is not installed here; it was read via GitHub.
- **Depth model code:** `DepthAnything/Video-Depth-Anything` (`run.py`, `utils/dc_utils.py`, `video_depth_anything/video_depth.py`).
- **ComfyUI's video decoder:** `comfy_api/latest/_input_impl/video_types.py`.

| Aspect | Official path | Ours before R2D (used by R2) | Ours now (R2D) | Evidence / confidence |
|---|---|---|---|---|
| Representation | VDA **relative** model: affine-invariant depth estimate | inverse planar depth (exact disparity) | same | Depth-family convention. The pinned sources do not *state* disparity in plain words, so **high confidence, not proven**. R2/R2D behaviour (near = bright → near object) is consistent with it. |
| Polarity | near = high value = white (`gray` colormap of the relative output) | near = white | near = white | as above |
| Normalisation | **global per-clip min–max** `(d−min)/(max−min+1e-6)` (`postprocess_gray`) | **per-clip p1–p99 percentile with clipping** | **per-clip min–max** over finite depth | node.py source: high |
| Per-frame vs per-clip | per clip | per clip | per clip | source: high |
| Metric vs relative | relative (the `vits` relative checkpoint, not `metric_*`) | relative (normalised) | relative | workflow JSON: high |
| Background / infinity | gets the clip minimum (dark) | 0 (black) | 0 (black) | source: high |
| Channels | 3 equal channels | 1-channel gray video → decoded as 3 equal channels | same | source + decoder test: high |
| Bit depth / format to the guide node | **float32 tensor, no quantisation, no codec** | 8-bit gray, **lossy H.264 yuv420p CRF 10** | 8-bit gray, **lossless full-range H.264 (yuvj420p, -qp 0)** | source: high |
| Resizing | lanczos to the output size (short side 544, then a multiple of 64), then the guide node's **bilinear** stretch to output/2 | we supply output size; the guide node does the bilinear stretch to 256×160 | same | iclora.py: high |
| Temporal | frames trimmed to 8n+1; VAE ÷8 (49 → 7 latent frames) | same | same | iclora.py: high |
| Internal preprocessing in the guide node | **none depth-specific**: bilinear resize, RGB[:3], VAE encode, ×2 dilation onto the latent grid | — | — | iclora.py: high |

**Decoder-measured codec error** (gray ramp plus moving block, decoded through ComfyUI's own `VideoFromFile.get_components`):

| Encoding | Max error | Mean error |
|---|---|---|
| R2's yuv420p CRF 10 | **3.68/255** | 0.57/255 |
| yuv420p qp 0 | 1.46/255 (limited-range rounding) | — |
| **yuvj420p qp 0 (now)** | **0/255** (exact) | — |

**Mismatches found and fixed** (`tools/admission/make_controls.py`, with tests):
1. p1–p99 percentile clipping replaced by the official per-clip min–max.
2. Lossy limited-range H.264 replaced by lossless full-range H.264.

**Their contribution to R2's "partial" result is unknown.** R2D changed several things at once (see §6), so this experiment does not isolate them.

The corrected control path is **aligned with the official preprocessing, not identical to it**. One documented residual remains: the official chain hands *float* frames to the guide node, while our video input is **8-bit** (exact after decoding, but quantised to 256 levels). The other difference is the depth *source*: an exact Blender depth pass instead of a VDA estimate, which is the point of the project.

## 2. Why R2 read as vague: the spatial evidence (measured from the R2 bundle)

At 512×320 the Union guide is resized to **256×160**: output ÷ `reference_downscale_factor` 2, as recorded in the LoRA header. The VAE then encodes it at ÷32 spatially and ÷8 temporally, so the whole control is **8×5 latent cells × 7 latent frames**, and one cell covers **64×64 output pixels**.

R2's diagnostic objects were at or below that resolution:
- **Cube:** 1.2–1.5 cells wide, 3–4 % of the frame.
- **Cone:** 0.6–1.2 cells, about 1 %.
- **Occluder pillar:** visible in about 1 of the 7 latent frames.

R2's prompt also *described* the motion, which confounds whether motion came from text or from control.

## 3. Diagnostic scene (deliberately plain)

`integrations/blender/build_control_diagnostic_scene.py`; assets are on G: at `G:\onecreations\renders\r2d_control_diag\`.

**Setup:**
- 512×320, 49 frames at 24 fps, **static camera** at (0, −10, 1.6) looking along +Y, 35 mm.
- Flat colours with the Standard view transform.
- Exact keyframes are in `diagnostic_spec.json`, copied to `admission_records/…_spec.json`.

**Objects:**
- **Red box** (2.4 × 1.0 × 1.6 m) at 7 m slides **LEFT → RIGHT**, x −2.3 → +2.3.
- **Blue ball** (r 0.8) floats above the box lane and moves **TOWARD the camera**, 15 m → 6 m.
- Gray floor, and a light wall at 20 m.

Outputs:
- the export bundle (raw planar depth, object index, camera/object matrices)
- `depth_control.mp4` with its sidecar
- `first_frame.png`
- `reference_preview.mp4`: Cycles OptiX, 64 spp, 26 s for 49 frames

## 4. Control validated before LTX (`tools/admission/control_diagnostic.py inspect`)

Checkpoint frames 0/12/24/36/48 (0/25/50/75/100 %):

| | f0 | f12 | f24 | f36 | f48 |
|---|---|---|---|---|---|
| Box GT centroid x (px) | 90.6 | 167.5 | 255.5 | 343.5 | 420.4 |
| Box width (cells) | 2.86 | 2.88 | 2.88 | 2.88 | 2.86 |
| Ball GT width (cells) | 0.84 | 0.97 | 1.19 | 1.50 | 2.09 |
| Ball area (% frame) | 1.35 | 1.88 | 2.78 | 4.52 | 8.69 |
| Ball depth (m) | 14.4 | 12.2 | 9.9 | 7.7 | 5.4 |
| Control intensity inside ball | 0.128 | 0.213 | 0.337 | 0.534 | 0.895 |

**Gate passed:**
- the box travels **5.15 cells**
- the ball's area grows **×6.42**
- the control brightens monotonically inside the ball

The control's range: the far wall (20 m) is 0 and the nearest floor (4.99 m) is 1.

**Tool check:** the colour tracker run on the Blender reference reproduces GT (box error ≤ 0.4 px; ball area ×6.43 vs 6.42), so the measurement method is validated before it is used on generated output.

## 5. R2D run — `ltx25-r2d-control-diagnostic` (one generation)

- **Graph:** `workflows/ltx25/r2d_control_diagnostic_api.json` is R2's exact graph:
  - INT8 ConvRot transformer + Gemma, video VAE
  - Union LoRA 1.0, guide strength 1, first-frame strength 1
  - stage 1, 8 distilled steps, `euler_ancestral`, CFG 1, seed 1000
- **Prompt:** the only other change is a **neutral, motion-free prompt** (objects only), so directed motion has to come from the control.
- **Conditions:** driver-default sysmem; Chrome closed; free RAM 23.5 GB at the start.
- **Input SHA-256:**
  - workflow `e7f4c0a9…`
  - first frame `7f933c0c…`
  - depth control `72b128fa…`
  - bundle `871134bd…`
- **Model SHA-256** (`model_registry/models.yaml`): `c4279eef…`, `6ce688a0…`, `847e14ca…`, LoRA `a1b888a8…`.
- **Output:** `ltx25_r2d_00001_.mp4`, SHA-256 `d0c70082…ebec42`.

| Telemetry | Value |
|---|---|
| Startup / generation | 6.6 s (warm file cache) / **33.1 s**: load 3.5, text encode 9.1, guide encode 0.5 + first frame 0.7, **denoise 17.2** (first step 12.2 s, median 0.594 s/step), decode 1.9, save 0.2 |
| Peak VRAM (device) | 11,943 MiB (DynamicVRAM design; same as R1/R2) |
| RAM | peak used 30,385 MB; **minimum available 2,124 MB** |
| Commit | peak 44,991 MB of 60,157 (**74.8 %**) |
| Pagefile | peak use 126 MB, growth **8 MB**: no paging |
| PCIe under load | gen4 x16 ×12, gen2 x16 ×1 (the known low-power weight-streaming window); width x16 throughout |

## 6. Objective analysis (`control_diagnostic.py compare`; rules fixed before the run)

| | f0 | f12 | f24 | f36 | f48 |
|---|---|---|---|---|---|
| Box generated centroid x | 90.4 | 170.4 | 257.5 | 344.7 | 419.7 |
| Box GT | 90.6 | 167.5 | 255.5 | 343.5 | 420.4 |
| Abs error (px; 1 cell = 64) | 0.2 | 2.9 | 2.0 | 1.2 | 0.7 |
| Ball generated area (px) | 2,209 | 3,095 | 4,555 | 7,422 | 13,688 |
| Ball GT area (px) | 2,218 | 3,072 | 4,550 | 7,412 | 14,233 |

**Box:**
- **Horizontal direction followed:** monotone, with 0 backward steps over 49/49 frames.
- **Travel:** 329.3 of 329.8 px (99.9 %).
- **Location within 1 cell** at every checkpoint, in fact within 3 px.

**Ball:**
- **Toward-camera trend followed:** area ×6.20 vs GT ×6.42.
- Non-decreasing, with 0 frame-to-frame dips over 10 % across 49/49 frames.

**Temporal ordering:** correct throughout.

**Visual inspection** of the reference / control / generated contact sheet (`G:\…\r2d_control_diag\analysis\compare_contact_sheet.png`) agrees. The generated video even adds the ball's cast shadow, which is not in the depth control.

**Similarity to the Blender reference:** PSNR 34.3 dB (min 29.9), SSIM 0.984. It is a close re-rendering, not a copy.

**Classification: PASS**: the major authored motion is unmistakably followed. Per the rule there was **no retry**, and no parameters were tuned.

**What this does and does not show:**
- **It shows** that LTX-2.5 + Union IC-LoRA, on this 4070 / 32 GB machine at 512×320×49, *can* follow a clear Blender depth signal to within a few pixels, with a neutral prompt.
- **It does not isolate** why R2 was vague. R2D changed three things at once relative to R2:
  - object scale and clarity relative to the 64-px guide cell (the leading hypothesis, given §2)
  - the depth normalisation and encoding fix
  - the motion-free prompt

  The individual contributions, including those of the two format deviations, remain **unknown**.
- **It does not test** camera motion, articulated or human motion, occlusion, textured or realistic scenes, or longer clips.

## 7. Storage (no hardware purchases: storage efficiency is architectural)

| | Before | After |
|---|---|---|
| G: free | 239.17 GiB | 239.16 GiB (this session added ≈ 10 MB on G:; no downloads) |
| C: free | 87.18 GiB | 87.11 GiB |

**Required, keep:**
- `models\` 36.33 GiB: 4 files (transformer, Gemma, VAE, Union LoRA), all registry-pinned and used by R1, R2 and R2D.
- `comfy\` 4.47 GiB: the pinned runtime.
- R2/R2D renders (0.03 GiB) and experiment outputs (< 0.01 GiB): benchmark evidence.

**Safely reclaimable** (reported, **not deleted**; owner approval needed):

| Item | Size | Notes |
|---|---|---|
| `G:\onecreations\temp\uv-cache` | **4.16 GiB** | torch/CUDA wheels; only needed to rebuild the ComfyUI env offline, and the pins are re-downloadable |
| `%TEMP%\oc_measure_*`, `oc_scene_check` | 0.03 GiB | old M1 scratch |
| `C:\…\Local\pip\cache` | 7.99 GiB | pre-existing and **the user's own**, not created by this project; reclaim only if the owner wants |
| `C:\Windows\SoftwareDistribution\Download` | 2.13 GiB | Windows-managed; not touched |

There are no duplicate model files, and the HF cache is 0.006 GiB.
