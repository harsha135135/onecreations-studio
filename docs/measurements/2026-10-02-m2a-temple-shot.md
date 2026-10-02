# M2-A — representative temple shot through the verified Blender → depth → LTX-2.5 path — 2026-10-02

**Question:** does the Blender → depth control → LTX-2.5 pipeline verified in R2D still work when the coloured-box diagnostic is replaced by a representative cinematic scene?

**Answer for this test: yes. M2-A = PASS** (one generation, no retry).

**Scope, stated precisely:** M2-A tests **whole-body rigid translation of a humanoid-shaped proxy** in a representative environment. The proxy has no articulation and no rotation. A pass is **not** evidence for articulated character or choreography control; that is M2-B.

All figures are **measured**, single observation, unless labelled otherwise.

**Constraints:**
- no hardware purchases; RTX 4070 12 GB + 32 GB RAM + existing storage
- no cloud, training, new downloads, Wan, FLUX, upscaler, 960×544 or 768×448 run
- no system changes
- one generation plus at most one evidence-driven retry

## 1. What changed vs R2D (one axis: synthetic → representative)

**Same as R2D:**
- 512×320 × 49 frames, static camera, rigid motion
- the graph: INT8 ConvRot transformer + Gemma, video VAE, Union IC-LoRA 1.0, guide strength 1, first-frame strength 1, stage 1, 8 distilled steps, `euler_ancestral`, CFG 1, seed 1000
- the corrected depth control (per-clip min–max disparity, lossless full-range)
- a neutral prompt
- driver-default sysmem

**New:** a representative environment and subjects.

**Why it is harder than R2D:**
- **Realistic, cluttered depth:** two colonnades (8 pillars), a stepped shrine, steps, walls, rubble, sky, instead of a floor and one wall.
- **Textured geometry and real lighting:** procedural stone and floor tiles, a warm low sun with long shadows.
- **Depth layering and occlusion:** the subject passes in front of the pillars and in front of a second figure.
- **A humanoid-shaped silhouette:** limbs, horns, an upright mace, a cloak, instead of a box.
- **A prompt that names stylised characters** ("demon warrior", "ascetic") that the primitive proxies do not look like.

## 2. Scene (`integrations/blender/build_temple_shot_scene.py`; assets on G: at `G:\onecreations\renders\m2a_temple\`)

**Camera:** static at (0, −10, 2.2), pitched 6° down, 35 mm, 512×320, 49 frames at 24 fps.

**Environment:**
- tiled stone courtyard (Brick Texture)
- pillars at x = ±3.2 (y −2 … 5.5)
- a raised shrine platform with steps, a stepped tower and a dark doorway
- side and back walls, and seeded rubble
- warm sun (energy 4) and a warm-gray sky (no blue, no fire)

**Primary subject:** `m2a_asura`, a crimson horned humanoid proxy (primitives joined into one rigid object), about 2.9 m to the horn tips and about 3.1 m to the top of the upright gold mace.
- **Authored motion:** LINEAR translation (−2.2, −3.5) → (1.3, −4.5) over frames 1–49, i.e. **left → right while approaching**, 6.3 → 5.3 m median depth.
- No rotation, no articulation.

**Secondary subject:** `m2a_shiva`, a static ash-blue ascetic proxy with a trident on the shrine platform (16.3 m). It is report-only and not a control target.

**Spec:** `shot_spec.json` (copied to `admission_records/2026-10-02_ltx25-m2a-temple_shot_spec.json`) holds the scene, the choreography and the **pre-registered tracking, gate and checks**, written before the run.

## 3. Control validated before LTX (`control_diagnostic.py inspect --spec`)

The control range is 5.03 m (white) → 23.2 m (black), with 5.3 % sky (black).

| Primary subject `m2a_asura` | f0 | f12 | f24 | f36 | f48 |
|---|---|---|---|---|---|
| GT centroid x (px) | 93.9 | 156.8 | 225.5 | 300.7 | 382.1 |
| bbox width / height (guide cells, 1 cell = 64 px) | 2.58 / 3.78 | 2.67 / 3.94 | 2.80 / 4.11 | 2.94 / 4.28 | 3.11 / 4.48 |
| area (cells; % frame) | 4.94; 12.3 % | 5.22 | 5.55 | 6.06 | 6.84; 17.1 % |
| median depth (m) | 6.27 | 6.02 | 5.77 | 5.52 | 5.27 |
| control contrast vs a 12-px ring | 0.41 | 0.50 | 0.57 | 0.57 | 0.51 |

**Gate passed:**
- coverage ≥ 2 cells (height, area) and ≥ 1.5 cells (width) at every checkpoint
- **travel 4.5 cells** in the authored direction
- control contrast ≥ 0.41 (gate 0.08)
- **the primary is never occluded**
- the colour tracker on the Blender reference reproduces GT: PASS. It sits a constant 7–9 px from the GT centroid because the gold mace and pauldrons are not "red".

**Occlusion periods:** the secondary figure (0.44 cells) is **partly occluded by the primary in frames 13–47**, about 68 % hidden at f36. That is the intended depth-layering test.

## 4. Run — `ltx25-m2a-temple` (one generation)

Launched with the new repo script `tools/windows/run_admission.ps1` (monitor + comfy_run).

**Hashes:**
- workflow `workflows/ltx25/m2a_temple_api.json` `320778ee…`: R2D's graph with only the neutral prompt and output prefix changed
- first frame `6a0a0a64…` (Blender frame 1)
- depth control `6b187c4f…`
- bundle `5ac57790…`
- models (registry): `c4279eef…`, `6ce688a0…`, `847e14ca…`, LoRA `a1b888a8…`
- **cache keys** (`tools/admission/experiment_keys.py` → `cachekeys`): control_render `ba16fb38…`, generation `83e1187f…`
- **output** `ltx25_m2a_00001_.mp4`, SHA-256 `fbb5fc09…dec732`

**Prompt** (neutral, with no motion direction or timing): "Cinematic shot of an ancient Indian stone temple courtyard at dusk: carved stone pillars, a raised shrine with a stepped tower, worn stone floor tiles. A towering crimson-skinned demon warrior with a heavy golden mace is in the courtyard; a pale blue-skinned ascetic with a trident is on the shrine steps. Warm low sunlight, long shadows."

**Conditions:** 512×320 × 49, seed 1000, guide strength 1, first-frame strength 1, LoRA 1. Chrome closed; 23.7 GB RAM free at the start.

| Telemetry | Value |
|---|---|
| Startup / generation | 7.2 s (warm cache) / **32.3 s**: load 3.4, text encode 8.6, guides 1.3, **denoise 16.9** (first step 12.0 s, then median 0.594 s/step), decode 1.9, save 0.2 |
| Peak VRAM | 11,949 MiB (DynamicVRAM by design; same as R1/R2/R2D) |
| RAM | peak used 30,444 MB; **minimum free 2,065 MB** |
| Commit | peak 44,872 MB of 60,157 (**74.6 %**) |
| Pagefile | peak 131 MB, **growth 19 MB**: no paging |
| PCIe under load | **gen4 x16 ×8** (no gen2 sample this run); width x16 throughout |

## 5. Analysis (`control_diagnostic.py compare --spec`, 0/25/50/75/100 %)

Contact sheet (reference / control / generated): `G:\onecreations\renders\m2a_temple\analysis\compare_contact_sheet.png`. Numbers: `admission_records/2026-10-02_ltx25-m2a-temple_compare.json`.

### Control fidelity (primary)

| | f0 | f12 | f24 | f36 | f48 |
|---|---|---|---|---|---|
| Generated centroid x (px) | 86.7 | 149.6 | 218.0 | 292.5 | 370.6 |
| Same tracker on the Blender reference | 86.8 | 149.2 | 217.6 | 292.4 | 373.5 |
| **Generated vs reference (like for like), px** | **0.0** | **0.3** | **0.4** | **0.1** | **2.8** |
| Generated vs GT, px (includes the 7–9 px tracker offset) | 7.2 | 7.3 | 7.4 | 8.2 | 11.4 |
| Generated area / reference-tracked area | 1.008 | 1.002 | 1.003 | 0.973 | 0.988 |

- **Direction:** left → right as authored. Monotone over **49/49** frames, with 0 backward steps.
- **Trajectory:** travel 283.9 / 288.1 px (**98.5 %**); every checkpoint is within 0.18 cells of GT and within 3 px of the reference.
- **Temporal ordering:** preserved throughout.
- **Depth trend (approach):** area ×1.351 vs GT ×1.385 (pre-registered threshold 1.193), non-decreasing, with no frame-to-frame dips over 10 %.
- **Occlusion and layering:** broadly agree. The primary passes in front of the pillars and in front of the secondary figure at the same times as authored (reference vs generated frame 30 match closely).

### Scene coherence (judged on gross spatial and structural relationships, with visual evidence)

- **Static structures:** pillars, shrine, steps, walls and floor tiling keep their layout and relationships across the clip. Visually, the contact sheet and a full-resolution f30 pair are nearly indistinguishable apart from softness.
- **Static-structure pixel drift (report-only, not a criterion):** generated mean |Δ| from frame 0 is 0.0028–0.0102, against 0–0.002 for the reference. That is ≤ 2.6/255, which is small.
- **Primary subject:** recognisable and stable all through. Tracked area is 0.97–1.01× the reference.
- **Caveat — secondary figure after occlusion:**
  - **Finding:** the small background figure (0.44 cells, well below the ~2-cell heuristic) is partly hidden by the primary for about 35 frames. In the generated clip it **re-emerges degraded at the end**: semi-transparent and ghosted, with its lower body smeared and the trident doubled. Its tracked blue area is 72 px against 172 px in the reference at f48; the reference dips during the occlusion too (161 → 79 → 172).
  - **Classification impact:** the major structure and the primary are unaffected, so this does not block judging the shot. It is the first evidence that **small, long-occluded secondary subjects do not recover cleanly** at this envelope.

### Visual quality (observations only; not a pass criterion at 512×320)

- The output is a close, slightly softer re-rendering of the Blender reference: PSNR 30.3 dB, SSIM 0.936 (R2D: 34.3 / 0.984, with simpler content).
- Shadows move with the subject. Texture detail on tiles and pillars is softened.
- **The proxies keep their primitive look.** LTX does not turn them into the prompt's "demon warrior" / "ascetic". At this configuration the character's look comes from the **first frame**, not from the prompt.

### Classification: **PASS**

The representative scene stays coherent enough to judge, and the major Blender-authored motion (lateral translation plus approach) is clearly followed. The pre-registered metric is PASS, and visual inspection agrees. **No retry** (rule).

## 6. What this means

- **Confirmed at this scope:** the R2D control path carries over from coloured boxes to a representative, textured, multi-layer environment, with the same runtime (about 32 s) and memory envelope (minimum free RAM about 2.1 GB, commit about 75 %, no paging). The pipeline is *Blender authors the geometry and motion; LTX-2.5 + Union depth control re-renders it*.
- **Look:** the first frame dominates appearance, so the eventual character and environment look must come from the first frame. That means a good Blender beauty render, or later an admitted keyframe model (FLUX.2-klein is not admitted yet). The prompt does not override it.
- **Not shown:** articulated or human motion, contact choreography, a moving camera, longer continuity, or higher resolution.
- **Caveat:** small secondary characters that are occluded for long stretches degrade. *Proposed:* keep important subjects at ≥ about 2 guide cells, keep long occlusions of small subjects out of single shots, or composite them from the Blender beauty pass (hard rule 8: the Blender path always delivers).

## 7. Proposed next controlled experiments (documented, **not run**)

Each changes one axis from M2-A, keeps the M2-A tooling, gate and analysis, and is classified PASS/PARTIAL/FAIL by pre-registered rules.

**M2-B — articulated character / choreography, static camera.**
- **Change:** the same temple, camera, envelope (512×320 × 49) and graph. Replace the rigid proxy with a **rigged humanoid proxy performing one clear articulated action**, for example a two-handed overhead mace strike or a step-and-raise, authored in Blender. This is the first use of the Session A armature/joint export and of `ActionTimeline` phases.
- **Coverage:** the actor ≥ 2 guide cells. The limbs that carry the action should span ≥ about 1 cell as they move; measure this in the pre-LTX gate.
- **Measures:**
  - whole-body trajectory (as in M2-A)
  - **limb or weapon timing:** the frame of the strike apex and contact in the generated video vs the authored event, from a coloured weapon head tracked like the M2-A subjects
  - pose plausibility (visual)
- **Out of scope:** no camera motion, no VFX.

**M2-C — authored camera trajectory, simple subject motion.**
- **Change:** the same temple and M2-A rigid proxy translation, plus **one authored camera move**: a slow dolly-in, or a short lateral track. It is defined as a `CameraMotion` and exported through the existing camera representation (camera samples digest → cache key).
- **Measures:**
  - parallax of static structures: pillar edges tracked in the generated video vs projected GT from the export, using the existing projection code
  - subject trajectory in screen space
- **Out of scope:** no articulation.

Only after M2-B and M2-C pass separately: combine them, the representative "pre-combat" shot with an articulated actor and a camera move.

## 8. Same-shot 768×448 comparison: **justified, documented, not run**

**Design:** the identical M2-A shot, re-rendered at **768×448 × 49**. Changing only the resolution needs:
- the same scene and spec (with the camera's horizontal FOV kept)
- `--resolution` on the export
- re-generated control and first frame (Cycles at 768×448)
- the identical graph except the latent size
- the same seed and strengths

**Questions it answers:**
- quality improvement: faces and detail, PSNR/SSIM vs reference, owner review
- control fidelity: the same pre-registered checks; the subject covers about 1.5× more cells
- VRAM, minimum free RAM and commit (RAM is the binding resource: about 2.1 GB free at 512×320)
- runtime

**Precondition:** an owner go-ahead. No upscaler; 960×544 is still deferred.

## 9. Storage

| | Before | After |
|---|---|---|
| G: free | 239.16 GiB | 239.14 GiB (renders 20.5 MB + run outputs 0.1 MB; no downloads) |

- No model files were added or duplicated: the 4 pinned files, 36.3 GiB.
- R1, R2, R2D and M2-A evidence is kept.
- The uv wheel cache (4.16 GiB) stays, as the owner allowed.
- Media, renders and `.blend` files stay on G:. Git holds only source, docs, tests and small JSON records.
