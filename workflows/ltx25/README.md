# LTX-2.5 admission workflows (ComfyUI API format)

These are run by `tools/admission/comfy_run.py` and wrapped by `tools/admission/monitor.py` (see `docs/runbooks/admission-ladder.md`).
The model files live on the data root (`G:\onecreations\models\ltx\…`) and are found through `G:\onecreations\comfy\extra_model_paths.yaml`.

| File | Rung | Source graph | Deviations from the official graph (and why) |
|---|---|---|---|
| `r1_t2v_video_only_api.json` | R1 T2V smoke | `ComfyUI-LTXVideo@3bf3ca62` `example_workflows/2.5/LTX-2.5_T2V_I2V_Single_Stage_Distilled.json` | see below |
| `r2_union_depth_api.json` | R2 first frame + depth Union control | `ComfyUI-LTXVideo@3bf3ca62` `example_workflows/2.5/LTX-2.5_ICLoRA_Union_Control_Distilled.json` | see "R2" below |
| `m2a_temple_api.json` | M2-A representative temple shot | same as R2 | R2D's graph with only the prompt (neutral: environment, style, subjects, lighting; no motion direction or timing) and the output prefix changed |
| `m2b_strike_api.json` | M2-B articulated strike (and its retry) | same as R2 | M2-A's graph and prompt; only the output prefix changed |
| `r2d_control_diagnostic_api.json` | R2D control diagnostic | same as R2 | R2's graph with only the prompt (neutral, motion-free) and the output prefix changed; see "R2D" below |

**R1 keeps the official values:** distilled 8-step `ManualSigmas`, `euler_ancestral`, CFG 1, `LTXVConditioning` at 24 fps, and tiled decode 512/64/128/32.

**R1 deviations:**
- **INT8 ConvRot** transformer and Gemma encoder replace the bf16 files. bf16 is 42 + 26 GB, which can't be resident on 32 GB RAM, and ConvRot is the route ADR-0001 and v1 §18 name.
- **512×320 × 49 frames** instead of 960×544 × 121. That is the R1 admission envelope.
- **Video-only:** no audio latent, audio VAE or audio decode. ComfyUI core runs the AV model with a zero-length audio stream (`comfy/ldm/lightricks/av_model.py` `separate_audio_and_video_latents`), and the owner staged downloads so the audio VAE is not fetched yet.
- **Prompt enhancer (Gemma-E2B) and the LTX API text-encode switch removed.** Prompts are fixed, and the run is offline and deterministic.
- **T2V only:** the image-to-video branch (`LTXVImgToVideoInplace`, `LTXVPreprocess`) is bypassed, as in the official T2V mode.
- The fixed prompt is stored in node 4. Seeds come from `comfy_run --seed 8/noise_seed=BASE` (job *i* uses BASE+*i*).

**R2** keeps the official Union graph's stage-1 settings:
- `LTXICLoRALoaderModelOnly` at strength 1, which supplies `latent_downscale_factor` (the LoRA header has `reference_downscale_factor: 2`)
- `LTXVImgToVideoInplace` at strength 1
- `LTXAddVideoICLoRAGuide` with frame_idx 0, strength 1, crop disabled, no tiled encode, tile 256/64
- the distilled 8-step sigmas, `euler_ancestral`, CFG 1
- `LTXVCropGuides` before decode, and the official tiled decode

**R2 deviations:**
- Everything listed for R1: INT8 ConvRot, 512×320 × 49, video-only, no enhancer or API encode.
- **Stage 1 only.** The official "Upscale and re-sampler (3 steps)" stage needs the spatial upscaler, which the owner excluded during admission (no upscale additions).
- **The depth control comes from Blender, not a preprocessor.** The official graph runs Video Depth Anything (or DW-pose/Canny) on a reference video. Here the control is the diagnostic scene's planar depth pass, converted by `tools/admission/make_controls.py`: inverse depth, per-clip p1–p99 normalisation, near = white. R2 used p1–p99 percentile clipping and lossy H.264 (CRF 10). Both were corrected for R2D, and their effect on R2 is unknown. The official expectation is in `docs/measurements/2026-10-02-ltx25-r2d-control-diagnostic.md` §1.
- **First frame:** a Blender Cycles render of frame 1 (128 spp, denoised, exposure −1.5 for legibility; the default exposure was nearly white). There are no materials, so it is a gray studio look.
- **Prompt:** it describes the diagnostic scene so that text, first frame and depth agree. The R2 inputs live in `G:\onecreations\renders\diag_512x320x49\`, which is passed to ComfyUI as `--input-directory`.

**R2D** (`r2d_control_diagnostic_api.json`) is node-for-node R2's graph. Only two inputs changed:
- The **prompt is neutral**: it names the objects but has no motion words, so any directed motion must come from the control.
- The **output prefix**.

Its inputs come from `integrations/blender/build_control_diagnostic_scene.py`, in `G:\onecreations\renders\r2d_control_diag\`:
- a static camera
- a red box sliding left → right
- a blue ball approaching the camera
- a depth control from the corrected `make_controls.py`: per-clip min–max disparity, lossless full-range H.264

This path is aligned with the official preprocessing except for the documented 8-bit video-input residual. Result: **PASS**, see the measurement doc.

**M2-A** (`m2a_temple_api.json`) is node-for-node R2D. The inputs come from `integrations/blender/build_temple_shot_scene.py`, in `G:\onecreations\renders\m2a_temple\`:
- a procedural temple courtyard
- a humanoid-shaped proxy under whole-body **rigid translation**
- a static secondary figure
- a static camera

Run it with `tools/windows/run_admission.ps1`. Result: **PASS**; see `docs/measurements/2026-10-02-m2a-temple-shot.md`.

**M2-B** (`m2b_strike_api.json`) is node-for-node M2-A, with the same prompt. The inputs come from `integrations/blender/build_temple_strike_scene.py` (`--strike-frames 9` for the retry), with references from `integrations/blender/render_reference.py`. They are in `G:\onecreations\renders\m2b_strike[_retry]\`:
- the M2-A temple
- a rigged humanoid proxy with a fixed root performing one **articulated** mace strike
- a static camera

Result: **PARTIAL** (both runs). Timing is followed to the frame, but the weapon smears in the fastest strike frames; see `docs/measurements/2026-10-03-m2b-temple-strike.md`.
