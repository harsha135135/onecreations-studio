# LTX-2.5 admission workflows (ComfyUI API format)

These are run by `tools/admission/comfy_run.py` and wrapped by `tools/admission/monitor.py` (see `docs/runbooks/admission-ladder.md`).
The model files live on the data root (`G:\onecreations\models\ltx\…`) and are found through `G:\onecreations\comfy\extra_model_paths.yaml`.

| File | Rung | Source graph | Deviations from the official graph (and why) |
|---|---|---|---|
| `r1_t2v_video_only_api.json` | R1 T2V smoke | `ComfyUI-LTXVideo@3bf3ca62` `example_workflows/2.5/LTX-2.5_T2V_I2V_Single_Stage_Distilled.json` | see below |
| `r2_union_depth_api.json` | R2 first frame + depth Union control | `ComfyUI-LTXVideo@3bf3ca62` `example_workflows/2.5/LTX-2.5_ICLoRA_Union_Control_Distilled.json` | see "R2" below |
| `m2a_temple_api.json` | M2-A representative temple shot | same as R2 | R2D's graph with only the prompt (neutral: environment, style, subjects, lighting; no motion direction or timing) and the output prefix changed |
| `m2b_strike_api.json` | M2-B articulated strike (and its retry) | same as R2 | M2-A's graph and prompt; only the output prefix changed |
| `m2c_camera_api.json` | M2-C authored camera move | same as R2 | M2-A's graph and prompt (verbatim); only the output prefix changed |
| `m3a_action_api.json` | M3-A controlled cinematic appearance | same as R2 | `m2b_strike_api.json` with only the prompt (cinematic appearance; no choreography or camera words, tested) and the output prefix changed |
| `m3b_character_api.json` | M3-B character / first-frame upgrade | same as R2 | `m3a_action_api.json` with only the output prefix and two node titles changed (prompt verbatim) |
| `m2b_strike_768_api.json` | M2-B same-shot resolution comparison | same as R2 | `m2b_strike_api.json` with only `EmptyLTXVLatentVideo` 768×448 (and the output prefix) |
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

**M2-B at 768×448** (`m2b_strike_768_api.json`) is node-for-node `m2b_strike_api.json` with only the latent width/height changed. Its inputs come from `build_temple_strike_scene.py --resolution 768x448`, in `G:\onecreations\renders\m2b_strike_768\`.

Two consequences follow from the resolution change and are left at pipeline defaults:
- **The Union guide grid** becomes 12×7 cells of 64 px (it was 8×5).
- **The official tiled decode** (tile 512, overlap 64) now really tiles.

The horizontal field of view is kept, so the vertical one narrows with the 1.714 aspect ratio. Result: admitted on the 4070 / 32 GB, but **no material improvement** for the fast weapon; see `docs/measurements/2026-10-03-m2b-resolution-768.md`.

**M2-C** (`m2c_camera_api.json`) is node-for-node M2-A/M2-B at 512×320, with the M2-A prompt verbatim (no camera words; tested). The camera motion comes only from the control. Inputs come from `integrations/blender/build_temple_camera_scene.py`, in `G:\onecreations\renders\m2c_camera\`:
- the M2-A temple
- the static M2-A proxy
- three colour banners on the left colonnade as parallax landmarks
- one authored `CameraMotion` (orbit + push-in, fixed 35 mm), keyed by `oc_import_camera`

Result: **PASS**; see `docs/measurements/2026-10-03-m2c-camera.md`.

**M3-A** (`m3a_action_api.json`) is node-for-node M2-B at 512×320 (8 steps, seed 1000, guide 1, first-frame 1). Only the prompt changes: it describes the cinematic look and has no choreography or camera words (word-boundary test). The new appearance signal comes from the **finished Blender first frame**, not from model settings. Inputs come from `integrations/blender/build_temple_action_scene.py` (look: `oc_lookdev.py`), in `G:\onecreations\renders\m3a_action\`:
- the M2-A temple, finished
- the M2-B strike at original speed on a finished demon
- a static finished ascetic
- an M2-C-type orbit + push-in
- deterministic layers (mace, dust), composited after generation by `tools/admission/hybrid_composite.py`

Result: **PARTIAL** (CONTROL PASS, APPEARANCE PARTIAL, hybrid v1 not fully usable); see `docs/measurements/2026-10-03-m3a-controlled-appearance.md`.

**M3-B** (`m3b_character_api.json`) is node-for-node M3-A: same prompt, seed, steps, strengths and size; only the output prefix (and two node titles) differ. The only input change is the first frame and the control rendered from `integrations/blender/build_m3b_scene.py` (the M3-A scene with the continuous characters of `oc_m3b_characters.py`), in `G:\onecreations\renders\m3b_action\`. Pre-registration: `admission_records/2026-10-03_ltx25-m3b-character_preregistration.json`. Not run yet.
