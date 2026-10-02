# LTX-2.5 admission workflows (ComfyUI API format)

These are run by `tools/admission/comfy_run.py` and wrapped by `tools/admission/monitor.py` (see `docs/runbooks/admission-ladder.md`).
The model files live on the data root (`G:\onecreations\models\ltx\…`) and are found through `G:\onecreations\comfy\extra_model_paths.yaml`.

| File | Rung | Source graph | Deviations from the official graph (and why) |
|---|---|---|---|
| `r1_t2v_video_only_api.json` | R1 T2V smoke | `ComfyUI-LTXVideo@3bf3ca62` `example_workflows/2.5/LTX-2.5_T2V_I2V_Single_Stage_Distilled.json` | see below |
| `r2_union_depth_api.json` | R2 first frame + depth Union control | `ComfyUI-LTXVideo@3bf3ca62` `example_workflows/2.5/LTX-2.5_ICLoRA_Union_Control_Distilled.json` | see "R2" below |

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
- **The depth control comes from Blender, not a preprocessor.** The official graph runs Video Depth Anything (or DW-pose/Canny) on a reference video. Here the control is the diagnostic scene's planar depth pass, converted by `tools/admission/make_controls.py`: inverse depth, per-clip p1–p99 normalisation, near = white. That convention is *proposed*, chosen to resemble Video Depth Anything's gray output, and has not been verified against it.
- **First frame:** a Blender Cycles render of frame 1 (128 spp, denoised, exposure −1.5 for legibility; the default exposure was nearly white). There are no materials, so it is a gray studio look.
- **Prompt:** it describes the diagnostic scene so that text, first frame and depth agree. The R2 inputs live in `G:\onecreations\renders\diag_512x320x49\`, which is passed to ComfyUI as `--input-directory`.
