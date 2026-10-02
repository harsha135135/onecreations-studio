# LTX-2.5 admission workflows (ComfyUI API format)

These are run by `tools/admission/comfy_run.py` and wrapped by `tools/admission/monitor.py` (see `docs/runbooks/admission-ladder.md`).
The model files live on the data root (`G:\onecreations\models\ltx\…`) and are found through `G:\onecreations\comfy\extra_model_paths.yaml`.

| File | Rung | Source graph | Deviations from the official graph (and why) |
|---|---|---|---|
| `r1_t2v_video_only_api.json` | R1 T2V smoke | `ComfyUI-LTXVideo@3bf3ca62` `example_workflows/2.5/LTX-2.5_T2V_I2V_Single_Stage_Distilled.json` | see below |

**R1 keeps the official values:** distilled 8-step `ManualSigmas`, `euler_ancestral`, CFG 1, `LTXVConditioning` at 24 fps, and tiled decode 512/64/128/32.

**R1 deviations:**
- **INT8 ConvRot** transformer and Gemma encoder replace the bf16 files. bf16 is 42 + 26 GB, which can't be resident on 32 GB RAM, and ConvRot is the route ADR-0001 and v1 §18 name.
- **512×320 × 49 frames** instead of 960×544 × 121. That is the R1 admission envelope.
- **Video-only:** no audio latent, audio VAE or audio decode. ComfyUI core runs the AV model with a zero-length audio stream (`comfy/ldm/lightricks/av_model.py` `separate_audio_and_video_latents`), and the owner staged downloads so the audio VAE is not fetched yet.
- **Prompt enhancer (Gemma-E2B) and the LTX API text-encode switch removed.** Prompts are fixed, and the run is offline and deterministic.
- **T2V only:** the image-to-video branch (`LTXVImgToVideoInplace`, `LTXVPreprocess`) is bypassed, as in the official T2V mode.
- The fixed prompt is stored in node 4. Seeds come from `comfy_run --seed 8/noise_seed=BASE` (job *i* uses BASE+*i*).
