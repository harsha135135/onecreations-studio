# M3-A — controlled cinematic appearance (first integration shot) — 2026-10-03

**Question:** can the pipeline substantially improve cinematic appearance while preserving the motion, timing, geometry and camera control already demonstrated by the diagnostic stages?

**Answer for this test: M3-A = PARTIAL** (one generation, no retry).
- **CONTROL: PASS**
- **APPEARANCE: PARTIAL**
- **Hybrid weapon protection (pre-registered v1): not fully usable**

All figures are **measured**, single observation, unless labelled otherwise. Generated viewpoint evidence is image-space only, as in M2-C.

**This is an integration test, not a one-variable admission test.** Several things change at once against the M2 diagnostics:
- the finished look
- articulation plus a camera move
- a second actor
- the hybrid weapon layer
- one effect

Each M2 capability was isolated first (R2D, M2-A, M2-B, M2-C), and the classification is split into two axes so that one cannot hide the other.

## 1. M2-C prerequisite / result

M2-C was already complete, committed and pushed (`4b2f3e8`, `docs/measurements/2026-10-03-m2c-camera.md`): **PASS**.
- **Landmarks:** three static landmarks follow their Blender trajectories (cos ≥ 0.994, 0.90× magnitude, ≤ 11.8 px).
- **Parallax:** ratios are reproduced within 0.6 %.
- **Framing:** within 7.7 px.

The camera evidence was sufficient to proceed, and no M2-C work was redone.

## 2. M3-A question

The question is whether the product promise works end to end in one short shot. The promise has three parts:
- authored 3D control
- generative cinematic appearance
- deterministic protection where the generative model is unreliable

**Division of responsibilities (kept explicit throughout):**
- **Blender** owns geometry, placement, rig and choreography, camera, exact timing, the contact, the weapon transform, object IDs, depth and the effect timing.
- **LTX** owns appearance, texture and detail synthesis, atmosphere, lighting interpretation and secondary motion.
- **The compositor** owns weapon protection, occlusion-aware integration and the deterministic effect layer.

## 3. Why appearance is now the primary gap

The external review's claims were checked against the repo and artifacts before being used.

| Claim | Verified? | Evidence |
|---|---|---|
| Outputs are 49 frames / 24 fps / ≈ 2.04 s | yes | every workflow: `EmptyLTXVLatentVideo` length 49, `LTXVConditioning` 24 fps → 49/24 = 2.0417 s |
| Eight sampling steps | yes | distilled 8-step `ManualSigmas` in every workflow; `denoise_steps.steps = 8` in the comfy reports |
| R1 is more cinematic than the controlled M2 shots | yes (visual) | R1 (T2V, no first frame) has a filmic look. The M2 shots copy their blockout first frames: the first frame, not the prompt, sets the look (M2-A finding) |
| R2D → M2-C give increasingly useful control evidence | yes | R2D PASS, M2-A PASS, M2-B PARTIAL, M2-C PASS (records) |
| M2-B's mace problem is concentrated in the fastest frames | yes | M2-B: timing 0/0 frames, smear only in the 3 fastest frames; the retry moved the smear with the fast frames |
| 768×448 did not materially fix the weapon | yes | `ltx25-m2b-strike-768`: worst fast-frame retention 0.117 vs 0.009, f25 still a ghost |
| Training spend should stay ₹0 | yes (policy) | budget ledger ₹0; no residual failure yet that training would address (§29) |

**Conclusion:** control had been shown capability by capability, but every controlled shot looked like geometric previs, because the first frame was a blockout render. Appearance under control was the untested product question.

## 4. Exact scene (`integrations/blender/build_temple_action_scene.py`)

**Environment:** the M2-A temple (same builders and geometry) re-surfaced with the new look-development module `integrations/blender/oc_lookdev.py` (§8).
- **Moved diagnostic banners**, flat cloth landmarks for the camera evidence, each a separate object with its own pass index:
  - NEAR: green 0.5 × 0.9 m, at (−3.2, −2.36, 3.25)
  - MID: magenta 0.62 × 1.2 m, at (3.2, 2.64, 3.25), yaw −12°
  - FAR: cyan 0.66 × 1.4 m, at (3.2, 5.14, 3.25), yaw −14.5°
- **Gold stays unique to the mace head:** the shrine finial is iron.
- **The M2-A static ascetic on the shrine is not present;** the defender replaces it.

**Primary actor `m3a_asura`** (pass 1), rig `m3a_asura_rig`:
- the M2-B 16-bone rigidly skinned rig and the M2-B strike keys verbatim, at original speed (6-frame strike)
- root fixed at the M2-B position (−1.8, −4.0)
- a finished body:
  - V-shaped torso with pectoral and abdominal forms
  - harness straps and collar, spiked iron pauldrons, elbow fillers
  - head with emissive eyes, tusks, curved ivory horns and a topknot
  - red cloth skirt
- **mace:** a spiked gold head `m3a_mace_head` (pass 8) and an iron shaft with grip bands `m3a_mace_shaft` (pass 9), bone-parented to `mace`

**Secondary actor `m3a_defender`** (pass 2):
- a static ascetic: dhoti legs, waist wrap, ash-blue skin, dark topknot, an iron trident held diagonally
- at (0.95, −4.55), yaw −90°, facing the demon, beside the impact point (−0.35, −4.3, 0)
- holds a defensive pose (allowed by the brief); it does not react

**Clearance:** camera ≥ 3.3 m from everything (the floor); the defender ≥ 5.76 m and the demon ≥ 7.09 m. The AABB proxies are OK.

## 5. ActionTimeline (`m3a_mace_slam_v1`, exact rational source time)

| Phase | Actor | Kind | Start → end (s) | Output frames |
|---|---|---|---|---|
| guard | asura | idle | 0 → 7/24 | 0–7 |
| windup | asura | other | 7/24 → 23/24 | 7–23 (**apex f23**) |
| strike | asura | strike | 23/24 → 29/24 | 23–29 |
| impact | asura | impact | 29/24 → 17/12 | **contact f29** → 34 |
| recovery | asura | recovery | 17/12 → 2 | 34–48 |
| defender_hold | defender | defense | 0 → 2 | 0–48 |

- **Actors:** `{asura: m3a_asura, defender: m3a_defender}`.
- **Agreement:** the GT screen events (apex 23, contact 29) and the 3D joint events (`mace` tail maximum height 2.957 m at f23, floor contact 0.34 m at f29) agree with the timeline exactly (0/0 frames).
- **Shape:** this is the brief's structure (guard 1–8, raise 8–23, downswing 23–29, impact ≈ 29, hold 29–35, recovery 35–49), reusing the verified M2-B choreography.

## 6. Camera trajectory (`CameraMotion` `m3a_orbit_push_in_v1`)

An M2-C-type move of the same family and difficulty (no escalation):

| | Start (f0) | End (f48) |
|---|---|---|
| Azimuth around the target (−0.85, −4.2, 1.6) | −12° | +12° (**24° orbit**, as M2-C) |
| Horizontal radius | 8.4 m | 7.0 m (**1.4 m push-in**; M2-C 1.5 m) |
| Height | 3.6 m | 3.3 m |
| Position (m) | (−2.597, −12.416, 3.600) | (0.605, −11.047, 3.300) |

- **Shape:** chord 3.50 m, path 3.53 m, peak 2.27 m/s (M2-C: 3.22 m, 2.07 m/s); 50 % linear + 50 % cosine easing; look-at with no yaw offset (the confrontation is centred); roll 0.
- **Lens:** fixed 35 mm, 36 mm sensor, AUTO fit, 512×320.
- **Representation:** the Session A chain, as in M2-C:
  - `look_at` → `CameraTrajectory` (`camera_motion.npz`)
  - → `CameraMotion` (`camera_motion.json`, SHA-256 pinned)
  - → `oc_import_camera` → `oc_export`
  - the samples are also recorded as CSV: `admission_records/…_camera_samples.csv`
- **Export check:** reproduces the authored motion within **4.6e-7 m / 2.3e-5°**, with the lens fixed and t = k/24 exact.

## 7. Appearance source

**Route A of the brief:** a finished Blender render of the same scene that produces the depth control.
- **No local image model exists:** `G:\onecreations\models\flux` and `\wan` are empty.
- Nothing was downloaded, and no dependency was added.
- **Route C** (repo tooling) is the same `render_reference.py`, so A and C coincide.

## 8. Finished-first-frame creation method

`integrations/blender/oc_lookdev.py` (bpy + stdlib only) builds a procedural, deterministic look on the unchanged geometry and camera. There are no image textures and no new assets.

**Materials:**
- **Stone:** two-tone noise, Voronoi cracks, dirt, optional fluting; flagstones with mortar.
- **Skin:** subsurface, pores, muscle shading.
- **Metal:** hammered and scratched gold and iron.
- **Cloth:** weave, sheen, folds; plus leather, ivory, eye emission, hair, white cloth, and dark beads (darkened so they never read as gold).

**World and lighting:**
- a dusk gradient sky (strength 0.35)
- a **bounded volumetric haze box** (density 0.006, an untagged volume-only mesh); a world volume was tried first and rejected because it blacked out the sky
- three-point lighting: warm low sun (energy 6, colour (1, 0.76, 0.52)), cool 600 W fill, 2,500 W rim

**Render look:** AgX "High Contrast", exposure −0.3.

**Render** (`render_reference.py --samples 256`):
- Cycles OptiX, seed 0, OIDN on the CPU, no motion blur
- frame 1 → `first_frame.png`; all 49 frames → the lossless `reference_preview.mp4`
- 102.2 s
- `first_frame.png` SHA-256 `1a98274a…6604dd`

**Character design** was improved in Blender geometry (the forms listed in §4). The characters are still built from primitives (ball joints, segmented limbs); see §15.

## 9. First-frame alignment gate

**Exact by construction:** `first_frame.png` is bit-identical to frame 0 of the Blender reference (max difference 0), and is rendered from the same `.blend`, camera and frame as the depth/object-index passes.
- **Same:** silhouettes, proportions, weapon location, floor contact and temple geometry.
- **No invented foreground and no pose contradiction:** none is possible.
- **Sheet** (`analysis/first_frame_alignment.png`: reference / first frame with object-index outlines / depth control with the same outlines): the outlines sit on the rendered silhouettes in both the beauty render and the control.

**Export-pass fix (before the gate):** the haze box initially speckled the 1-spp export depth and object-index passes (7,694 noisy px).
- **Fix:** `oc_export` now hides volume-only helpers while rendering the geometric passes and records them in `passes.excluded_volume_objects` (here `["lk_haze"]`).
- **After:** 0 isolated background pixels (Blender-tested); only 136 edge pixels differ.
- **Elsewhere:** the M2 scenes have no volumes, so their exports are unchanged (tests pass).

**Pre-LTX gate (`control_diagnostic.py inspect --spec`): PASSED.**

| Check | Result |
|---|---|
| Joints | the projected `mace` tail lies within 0.62 px (median 0.32) of the head's object-index centroid; root and legs move 0.0 m |
| Timeline | GT screen and 3D events = timeline (apex 23, contact 29), 0/0 frames |
| Camera contract / clearance | 4.6e-7 m, 2.3e-5°, lens fixed / min 3.3 m (floor), proxies OK |
| Demon | 1.8–2.3 cells wide, 2.7–3.1 tall, 2.1–2.7 cells area, never occluded (own mace ignored), control contrast ≥ 0.30 |
| Mace head | about 0.8 cell, vertical excursion 2.6 cells, visible in 49/49 frames, contrast 0.11 (apex) / 0.59 (contact) |
| Landmarks | NEAR / MID / FAR GT displacement 39.4 / 129.0 / 136.3 px; visible area ≥ 0.96 / 0.82 / 0.757 of max |
| Parallax signal | NEAR vs FAR 39.4 vs 136.3 px (ratio 3.46). MID is not a separate parallax layer: on this move it moves like FAR (129 vs 136 px) |
| Trackers on the finished reference | timing 0/0 frames; trajectories within ≤ 0.9 px; demon position within 2.3 px |

**Diagnostic adaptations for the finished look (all before generation, recorded in the spec):**
- **Colour rules:** under the finished look the blockout colour rules misfire: the cyan banner renders teal (≈ (153, 210, 198); `cyan` finds 0 px), `red` fires on the dark-gold mace, and `gold` fires on warm stone. New rules:
  - `crimson`: r > 70, r > 2.2 g, r > 2.2 b
  - `gold_deep`: r > 90, g > 45, r ≥ g, g > 0.45 r, b < 0.3 g
  - `teal`: g > 100, b > 90, g − r > 40, b − r > 30, g < 1.35 b, b < 1.2 g

  They were validated on the reference and are unit-tested on the rendered colours.
- **Banners:** relocated to the right colonnade and enlarged, because MID and FAR were occluded and FAR was too small for this camera.
- **`approach` (area-growth) check dropped for the demon:** on the finished reference the red-mask area does not reproduce GT growth (×1.11 vs ×1.27; armour, harness and arm occlusion), so only `position` was kept. This is recorded in `tracking.notes`. **The `control_pass` sentence still mentions "position + approach"; the registered checks are `position` only** (the spec was not rewritten).
- **Defender:** the `blue` rule finds 1–10 px of the defender under warm light (GT 3,512–5,632 px), so the defender is report-only and visual.

## 10. Baseline controlled appearance

Existing artifacts are used as baselines; no extra generation was spent:
- **Action:** `ltx25-m2b-strike` (raw 512×320: the same strike, static camera, blockout look).
- **Camera:** `ltx25-m2c-camera` (raw: the same move family, static subject, blockout look).

Neither matches M3-A exactly (M2-B has no camera move; M2-C has no strike), so the comparison is at matched beats. The sheet is `analysis/appearance_m2b_m3a_m2c.png`.

## 11. Blender reference (A)

- **Sharp reference:** `reference_preview.mp4`, 256 spp, finished look; this is the authored truth.
- **Matched motion-blur reference:** `reference_motionblur.mp4`, same render with Blender motion blur, shutter 0.5 frame (180°), centred; 106.5 s.
- **With the effect:** `analysis/hybrid/reference_with_effects.mp4` is the sharp reference with the dust layer composited.
- **Contact sheets:** the inspect checkpoint and event sheets, plus the A/B/C key-frame sheets in `analysis/hybrid*/`.

## 12. Raw LTX result (B)

**Run `ltx25-m3a-action`:** one generation, `workflows/ltx25/m3a_action_api.json`, output `53452400…1e051af`.
- **Workflow:** identical to `m2b_strike_api.json` except the prompt and the output prefix. That means 512×320×49, 8 steps, seed 1000, INT8 ConvRot, Union IC-LoRA 1, guide strength 1, first-frame strength 1, the corrected depth control and driver-default sysmem. No model setting changed.
- **Prompt:** appearance only. A word-boundary test found no choreography or camera words.

  > "Cinematic fantasy film still of an ancient Indian stone temple courtyard at golden hour: weathered carved stone pillars, a stepped shrine tower, worn cracked flagstones, soft volumetric haze and drifting dust in warm low sunlight with long shadows. A towering crimson-skinned demon warrior with curved ivory horns, tusks and glowing eyes wears spiked dark iron pauldrons, a leather harness and a red cloth skirt and holds a heavy golden spiked mace. Facing him stands a pale ash-blue skinned ascetic in a white dhoti with a dark topknot, holding an iron trident. Highly detailed textures, dramatic cinematic lighting, subtle film grain."

**What it shows:**
- the authored strike and camera move in the finished look: dusk light, haze, warm stone, crimson demon, gold mace, ash-blue ascetic
- softer than the reference; fine procedural texture (stone cracks, banner weave) is largely lost
- the mace breaks down in f25–27 (§17)

**Hashes:**
- workflow `36bc5c95…`, first frame `1a98274a…`, control `ff547e9e…`, bundle `1fbaaf19…`
- cache keys: control_render `78533586…`, generation `fda30137…`

## 13. Hybrid composite (C)

`tools/admission/hybrid_composite.py` combines the raw video with the deterministic layers declared in the spec's `layers` section, a new `CompositeManifest` contract (§20).
- **Outputs** (`analysis/hybrid/`):
  - `hybrid.mp4`
  - `reference_with_effects.mp4`
  - `composite_report.json`
  - A/B/C sheets `abc_key_frames.png` (guard 4, wind-up 14, apex 23, fast 25/26, pre-impact 28, impact 29, hold 32, recovery 40, final 48), `abc_strike_strip.png`, `strike_zoom_A_B_C_f23_f30.png`, `mace_zoom_sharp_blur_raw_hybrid.png`
- **Visual result (v1, pre-registered):**
  - the protected f23–29 show a solid gold mace on the authored path, with the shaft restored and attached to the generated hand, and a directional motion-blur streak
  - outside f23–29 the frames are the raw LTX frames untouched (plus the dust from f29)
  - **but** at f26–27 the raw orange blob remains visible through the semi-transparent blur streak, a **double image**
- **Post-hoc v2** (`analysis/hybrid_v2/`, `--ghost-under-layer`): it also inpaints raw remnants under the layer's partial alpha. It removes most of the double image; some orange tint remains at f27. It is **labelled post-hoc** and is not used for the pre-registered class.

## 14. Control-axis evaluation (raw LTX output, pre-registered checks)

| Element | Check | Result |
|---|---|---|
| ActionTimeline timing | mace `timing` | **apex 23 / contact 29 = GT (0/0 frames)**; excursion 167 px = **1.005×** GT; detected 49/49; peak speed f26 (GT f25) |
| Actor placement / framing | demon `position` | displacement from f0 within **4.1 px** of GT at every checkpoint (limit 32); area within **3.8 %** (limit 25 %) |
| Camera progression, NEAR | `trajectory` | cos 0.993, magnitude 0.906, ≤ 5.7 px (limit 16), monotone, max step 1.5 px |
| Camera progression, MID | `trajectory` | cos 0.9995, magnitude 0.985, **checkpoint error 23 px at f36 (limit 38.7), progress lag 0.175 (limit 0.25), max backward step 0.091 (limit 0.1)**: followed, but near the limits |
| Camera progression, FAR | `trajectory` | cos 0.9994, magnitude 0.974, ≤ 5.9 px (limit 40.9), monotone |
| Relative parallax | `parallax` NEAR/FAR | order agrees; normalised NEAR 0.269 vs GT 0.289; ratio 3.72 vs 3.46 (within ×/÷1.35) |
| Metric class | — | **PASS** (all primary checks followed) |

**MID landmark jitter:** in f30–42 its tracked x wobbles (≈ 415 → 427, 426, 414, 423 …). The crop sheet `analysis/mid_banner_f30_f42.png` shows the generated magenta banner's edge softening and bleeding into the adjacent pillar, not a jump of the banner. It is a tracker-on-soft-edge effect plus slight temporal shimmer, recorded as a non-critical degradation.

**Visual (documented inspection of the contact sheets and the clip):**
- **Action:** readable.
- **Arm:** the weapon arm visibly changes pose through guard → wind-up/apex → strike/contact → recovery. The mace does not move independently, and the actor does not translate.
- **Impact:** lands on the authored beat (f29).
- **Camera:** the orbit and push-in progression is coherent; the pillars' overlaps change in reference order.
- **Environment:** coherent (pillars straight, banners attached, shrine stable), though softened.
- **Raw weapon:** smeared in f25–27 (§17). This is the known M2-B limitation and the reason for the hybrid layer; the pre-registered CONTROL axis judges articulation, timing, camera and framing on the raw output, and the weapon's raw shape is handled by the hybrid criterion.
- **Defender:** stays in place and keeps its pose and colours (visual; the colour tracker is not usable, §9).

## 15. Appearance-axis evaluation

Compared at matched beats with the blockout baselines (`appearance_m2b_m3a_m2c.png`, A/B/C sheets):

**Materially improved:**
- **Lighting:** warm low sun, long shadows, cool fill and rim separation, dusk sky.
- **Atmosphere:** haze with depth falloff.
- **Contrast:** filmic (AgX High Contrast) instead of flat Standard.
- **Materials:** weathered stone with colour variation, readable flagstones, metallic gold and iron, cloth, skin shading.
- **Character design:** horns, tusks, pauldrons, harness and skirt on the demon; a recognisable ascetic with a trident.

The M2 blockouts have flat, uniformly lit primitives with saturated plain colours.

**Not achieved:**
- **The characters still read partly as primitive or stylised figures:** ball joints, segmented capsule limbs, a toy-like proportion. The appearance gain comes from the first frame; LTX reproduces the first frame's look rather than adding realism or new detail.
- **Fine texture does not survive generation.** Report-only metrics (`…_appearance_metrics.json`), mean |Laplacian| in the environment:
  - the finished reference has 12.7–13.0 vs 8.6–8.8 for the M2-B blockout reference
  - the raw M3-A output has 7.0–8.1, about the same absolute high-frequency level as the raw M2-B output (8.0–8.3)
  - the improvement is in light, colour, materials and design (low and mid frequencies), not in fine detail
- **Fidelity to the reference** is lower than for the blockout, as expected for richer texture under a moving camera:
  - environment detail ratio raw/ref 0.62 at f0, then 0.52–0.58
  - actor 0.87 at f0, then 0.64–0.74
  - PSNR vs reference 30.0 → 18.8 dB (M2-B 32.4 → 27.6, static camera)

## 16. Appearance persistence

Inspected at frame 1, guard (4), wind-up (14), apex (23), fast swing (25/26), impact (29), hold (32), recovery (40) and final (48):

| Property | Persistence |
|---|---|
| Costume / armour | persists: pauldrons, harness, skirt and horns are visible in every inspected frame |
| Body silhouette | persists; it follows the rig |
| Face / head | eyes, horns and tusks persist at this scale; there is no facial detail to lose |
| Dominant materials / colours | actor mean colour raw vs ref within ≈ 4 RGB at every inspected frame (e.g. f0 (141, 57, 33) vs (146, 56, 31); f48 (128, 51, 30) vs (129, 50, 28)); it does not drift toward blockout |
| Weapon design | spiked gold head holds in slow frames; broken in f25–27 (§17) |
| Lighting language | warm key, shadows and haze persist f0–f48 |
| Temple material richness | stone colour and lighting persist; fine cracks are already softened in the decoded f0 (detail ratio 0.62), fall to 0.53 by the apex, then hold (0.52–0.57) |

The finished look **does not collapse toward the blockout during motion**. Its fine texture is softened from the first decoded frame and then holds steady.

## 17. Mace/shaft raw-generation behaviour

- **Slow frames** (guard, wind-up, hold, recovery): a solid spiked gold head on an iron shaft held in the hand.
- **f25–27** (authored head speed up to 65.8 px/frame, about 1.3 head widths/frame):
  - the raw mace becomes an amorphous gold/orange blob instead of a directional streak
  - the shaft–hand link is lost
  - f27 has a red-orange tint
- **f28–29:** the head re-forms at the contact.
- **Area metric:** within a band around the authored silhouette, raw/reference retention stays ≥ 1.08 against the blur-matched reference on all frames (no low-retention frames). Against the sharp reference it is 0.577 at f25. **In this run the area metric misses the shape breakdown:** the blob has gold-coloured area but not mace shape. Its numbers are not comparable to M2-B's 0.009, which used a different look and colour rule.
- **Same failure class as M2-B and the 768 run:** the fastest strike frames lose the weapon's structure, while timing and arm articulation hold.

## 18. Blender motion-blur comparison

- **Configuration:** Blender motion blur, shutter 0.5 frame (180°), position CENTER, same authored motion, same 256 spp (`reference_motionblur.mp4`). The sharp reference and the first frame have no blur.
- **Expected displacement:** the head moves up to 65.8 px/frame (GT, f25), so a 180° shutter smears it over ≈ 33 px.
- **What legitimate blur looks like:** the blur reference shows a directional streak along the arc with the head shape readable at the leading end. The shaft is faint but continuous and stays attached to the hand.
- **Legitimate blur alone cuts the sharp-referenced gold area:** the blur reference's own retention vs sharp is 0.997 / 0.976 / 0.872 / 0.535 / **0.29** / 0.662 / 0.937 / 0.982 at f22–29.
- **Conclusion:**
  - part of the M2-B "area loss" was legitimate blur, which is why the protected-frame and retention rules are measured against the blur-matched reference
  - the raw LTX f25–27 blob is **not** legitimate blur: no direction along the arc, no shaft, no hand attachment
  - the blur check does not excuse broken weapon topology

## 19. Protected frame interval

The rule is in the `CompositeManifest`, pre-registered:
- frames where the authored head speed into or out of the frame is ≥ 0.5 × its own width, from GT, dilated by 1 frame
- **plus** any frame whose raw retention vs the blur reference is < 0.5 (data-driven, anywhere in the shot)

**Result:**
- **Authored:** f24–28 fast, dilated to **f23–29** (the recovery peak is only 0.34 widths/frame)
- **Data-driven additions:** none (no low-retention frames)
- **Protected: f23–29 (7 frames).** The whole action interval was inspected, not only f25.

## 20. Compositing method

**`CompositeManifest`** (`src/onecreations/contracts/composite.py`, schema `composite_manifest.schema.json`). Each layer declares:
- what renders visible (`objects` or `collections`)
- how: holdouts, motion-blur shutter, samples
- `occlusion: holdout`
- the `protection` rule or the effect `trigger` (an ActionTimeline phase edge) and duration
- grading and ghost suppression

**Layers rendered by `integrations/blender/render_layers.py`** from the same `.blend`:
- **`mace_protect`:** mace head + shaft visible; the other 52 meshes are holdouts; haze hidden; transparent film; 64 spp; motion blur 0.5 frame centred; 49 RGBA frames; 33.7 s
- **`impact_dust`:** the `fx_impact` collection; 14 frames, Blender 30–43; 10.5 s

**Per protected frame, `hybrid_composite.py`:**
1. **Grade:** a per-channel gain fitted once from raw vs layer colour over well-reconstructed (slow) frames: [0.965, 0.965, 0.858] (a minimal relighting approximation, no relighting model).
2. **Ghost suppression:** inpaint raw gold remnants near the authored path, outside the layer's solid core. v1: only where layer alpha < 77; v2 (post-hoc): also under partial alpha.
3. **Alpha-over** the straight-alpha layer.
4. **Outside protected frames:** the raw frame is kept untouched.

**Pre-registered hybrid criterion, calibrated by a dry run before generation:**
- **Dry run:** compositing the layer over the blur-matched reference itself measures the tool's own on-path error: 0.1–1.5 px, 5.7 px at f26 from thresholding a blur streak.
- **On-path:** per protected frame, the composite's weapon centroid must be within (dry-run error + 3 px) of the blur reference's.
- **Attachment:** the projected grip must be within 12 px of generated crimson hand pixels.
- **Plus:** solid, correctly occluded, no obvious halo or double image.
- **Report-only:** the error against the sharp GT, which motion blur alone biases by up to 6.4 px.

| Frame | 23 | 24 | 25 | 26 | 27 | 28 | 29 |
|---|---|---|---|---|---|---|---|
| v1 on-path error / limit (px) | 0.8 / 3.1 | 0.8 / 3.6 | **5.6 / 4.5** | 6.9 / 8.7 | **6.5 / 4.2** | **4.1 / 4.0** | 1.5 / 3.3 |
| v1 grip → generated hand (px, limit 12) | 0.3 | 0.6 | 0.2 | 2.9 | 0.3 | 0.4 | 0.4 |
| v1 ghost px inpainted | 694 | 371 | 263 | 557 | 667 | 1,139 | 1,410 |
| v2 (post-hoc) on-path error / limit (own dry run) | 1.0 / 3.2 | 0.9 / 3.2 | 2.9 / 4.8 | 2.0 / 8.8 | 1.3 / 4.6 | 0.4 / 4.0 | 0.4 / 3.3 |
| v2 ghost px inpainted | 1,934 | 1,761 | 1,037 | 1,422 | 1,991 | 2,572 | 2,613 |

- **v1:** over the on-path limit at f25, f27 and f28, which is the raw blob pulling the tracked centroid, plus the visible double image → **not fully usable**.
- **v2:** within every limit, with grip ≤ 2.9 px. It is post-hoc, so it is not used for the class.

## 21. Occlusion handling

**Method:** layers are rendered with every non-layer mesh as a Blender **holdout**. Holdouts still occlude the layer and still cast shadows and bounce light on it, but they render transparent, so occlusion by the actor or the environment is exact Blender visibility, not a 2D depth test. No opaque paste is used.

**Measured layer vs object-index GT:**
- **Slow frames:** layer (alpha > 128) vs the visible mace pixels have IoU 0.971–0.996 (median 0.992). At most 14 px fall on other objects, and at most 3 visible mace px are missed.
- **Fast frames f22–30:** IoU 0.941–0.996; the legitimate blur spreads alpha beyond the sharp silhouette.
- **Body:** layer alpha on demon-body pixels in slow frames is 0–1 px, so the hand and body correctly hide the shaft where they are in front.
- **Mace head:** never occluded in GT in this shot, so occlusion *behind* scene geometry is shown only for the shaft at the grip.
- **Dust:** the dust layer uses the same holdout rule (all 12 non-effect meshes), so the actors and the mace occlude it by construction.

**Gaps:**
- the defender is not in front of the weapon at any frame, so actor-in-front-of-weapon occlusion is not exercised
- halo: no hard cutout edge is visible at the inspected zooms, but the semi-transparent blur edge exposes raw remnants (§13)

## 22. Impact effect timing

**The one effect:** a small dust puff plus chips at the impact point, in the `fx_impact` collection (excluded from the main view layer, so it never enters the first frame, control or reference). It has:
- 30 puffs with a shared material whose alpha is keyed 0.7 → 0 over 14 frames
- 12 chips, CONSTANT interpolation
- deterministic geometry, no simulation

**Trigger:** `trigger: {timeline: m3a_mace_slam_v1, phase: impact, edge: start}` resolves to source 29/24 → **output frame 29**, exactly the authored contact. LTX does not decide the timing.
- **Measured:** the layer's first visible frame is output 29 (114 px with alpha > 10), growing to 17,557 px by f42 while fading. The duration is 14 frames (29–42).
- **Visual:** the dust appears on the contact beat in A and C and fades through the hold.

## 23. Runtime / resources

| Telemetry | Value |
|---|---|
| Generation | **32.9 s**: load 3.5, text encode 8.8, denoise 17.1 (first step 12.2 s, then median 0.594 s/step), decode 2.0 |
| Startup / end to end | 7.1 s (warm cache) / 41.4 s |
| Peak VRAM | 11,949 MiB (DynamicVRAM by design) |
| RAM | peak 30,439 MB; **minimum free 2,070 MB** |
| Commit | peak 45,931 of 60,157 MB (**76.4 %**) |
| Pagefile | baseline 97 MB, peak 174 MB, **growth 77 MB**: no paging pressure |
| PCIe under load | gen4 x16 ×10, plus one gen2 x16 sample (the known weight-streaming window); the monitor flags are the expected `gpu_over_target` and that sample |
| Baseline before the run | 23.57 GB RAM free, commit 17.3 %, pagefile 97 MB in use, Chrome closed; Edge background processes about 290 MB (noted, not closed); updates paused until 2026-10-09 |

**Blender (not generation):**
- reference at 256 spp: 102.2 s
- motion-blur reference: 106.5 s
- mace layer: 33.7 s
- dust layer: 10.5 s
- scene build + export with passes: about 19 s (Blender test)

**Storage:**
- G: 238.97 GiB free at the start of M3-A work, 238.84 before the run, **238.76 after** (renders 234 MB: the final pre-gate build and its analysis, since earlier development builds were deleted before the gate; run output 156 KB)
- **no downloads**
- **₹0 spent**

## 24. Retry, if used

**None.** The retry rule allows one evidence-driven retry when the integration class is not FULL PASS and **one dominant, fixable cause** is identified. Neither residual is a generation problem:
- **APPEARANCE PARTIAL:** the cause is the first frame's character modelling (primitive figures). Fixing it is a scene and design change, not a retry of the same experiment.
- **Hybrid v1:** the cause is the compositor's ghost-suppression rule, which is deterministic. A generation retry cannot fix it, and changing prompt, seed, steps or strength to chase the weapon is excluded by the brief. The deterministic fix was evaluated as a labelled post-hoc v2 on the same raw output.
- **CONTROL:** passed.

## 25. CONTROL classification: **PASS**

- **Raw output:** every pre-registered primary check is followed: timing, position, three landmark trajectories, parallax.
- **Visual:** the action stays readable, the arm articulates through every phase, the impact lands on the beat, the camera progression is coherent, and the environment is coherent.
- **Non-critical degradation recorded:** the MID landmark's late jitter, within the limits.

## 26. APPEARANCE classification: **PARTIAL**

Two parts of the PASS definition are not met:
- **"Characters no longer read primarily as primitive geometry":** they read partly as stylised primitive figures.
- **The transformation is the first frame's look:** LTX adds no realism or detail, and fine texture softens.

**Met:**
- materially more finished than the blockout baselines
- temple material, lighting and atmosphere richness materially improved
- the look persists through the whole shot without collapsing toward the blockout
- temporally coherent enough to be useful

## 27. Overall M3-A classification: **PARTIAL**

FULL PASS needs CONTROL PASS + APPEARANCE PASS + usable hybrid protection; two of the three are missing (APPEARANCE PARTIAL, hybrid v1 not fully usable):
- **CONTROL:** PASS
- **APPEARANCE:** PARTIAL
- **Hybrid (pre-registered v1):** not fully usable. The mace is solid, attached and on time, but there are on-path overshoots at f25/f27/f28 and a visible double image in f26–27.
- **Hybrid post-hoc v2:** within all limits, with residual tint at f27. Reported, not counted.
- **Owner playback verdict:** not required; record it here separately if given.

## 28. Remaining limitations

- **Single observation:** one shot, one seed, 49 frames, 512×320.
- **Character design:** the procedural Blender characters are the appearance ceiling. With no local image model, the first frame can't be made more realistic than the Blender modelling.
- **LTX at this envelope** keeps the first frame's light, colour and materials but not its fine texture. It is untested whether more steps, 768×448 or a higher-detail first frame change this; none was run.
- **The raw fast weapon still breaks** (f25–27). This is unchanged from M2-B; the hybrid layer is required for weapon-critical frames.
- **The hybrid needs the v2 ghost rule:** it must be pre-registered and re-validated on a new shot before it counts. The f27 tint remains.
- **Relighting:** a global per-channel gain only. The layer has Blender lighting, not LTX's lighting interpretation.
- **Occlusion:** actor-in-front-of-weapon occlusion was not exercised.
- **Defender:** static; there is no reaction and no contact.
- **Not a full parry:** no two-character contact and no camera escalation.
- **Diagnostics:** under finished looks they need per-look colour rules (crimson / gold_deep / teal), validated on the reference first. The area-retention metric misses shape breakdown of a same-coloured blob.
- **The `approach` framing check** was not usable on the armoured demon; framing evidence is `position` only.

## 29. Whether training is justified yet

**No.** Nothing here is a repeatable generative failure that a trained adapter would be the right fix for:
- control holds on the raw output
- the appearance limit sits upstream, in the first frame's character modelling
- the weapon failure is handled deterministically by design (hard rule 8)
- the residual hybrid artifact is a compositing rule

Training stays at ₹0. It becomes a question only if a specific residual failure repeats after the first-frame and compositing fixes.

## 30. Next milestone recommendation (proposed, not started)

**M3-B: character / first-frame appearance upgrade + a pre-registered hybrid v2**, on the same M3-A shot, controls and timeline, before any two-character parry:
1. **Raise the first frame's character quality without changing the control.** Better Blender character modelling (continuous body meshes instead of primitives, sculpted forms, costume detail) on the same rig and silhouettes, so the depth control and timing stay valid.

   A local image-model route stays an owner decision (no automatic download). It would need an alignment gate that is no longer exact by construction.
2. **Pre-register hybrid v2** (ghost suppression under partial alpha) and validate it on that shot. Add an actor-in-front-of-weapon occlusion case if the choreography allows.
3. **Keep the M3-A configuration** (512×320 × 49, 8 steps, seed 1000), with one generation and at most one evidence-driven retry.

Only after an APPEARANCE PASS with usable hybrid protection: the two-character parry (V1's "one readable parry").
