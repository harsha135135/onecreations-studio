# OneCreations Studio — status and handoff

> **Read this first on the Windows desktop.** It is the single source of truth for where the project is,
> what comes next, and the rules that cannot be broken. Update it at the end of every work session
> (see "How to update this file").

| | |
|---|---|
| **Last updated** | 2026-10-06 (night): Windows desktop, **D1 autonomous director foundation** (prompt -> DirectorPlan -> ShotSpec -> CompiledShot -> Blender preflight) |
| **Current phase** | **M0, M0.5 and M1 complete** (G0 passed). **M3 in progress:** LTX-2.5 R1, R2 and **R2D** measured at 512×320×49. R1 pass; R2 partial on motion clarity; **R2D control diagnostic PASS**: an unambiguous Blender-authored motion is followed to within 3 px. **M2 in progress:** **M2-A PASS**: whole-body rigid translation of a humanoid-shaped proxy is followed in a representative temple scene. **M2-B PARTIAL** (2 runs): an articulated strike's timing is followed to the frame and the arm follows every phase, but the fast-moving weapon smears. **M2-B @ 768×448: admitted, NO MATERIAL IMPROVEMENT** for the fast weapon (one generation, only resolution changed). **M2-C PASS**: a moderate authored camera move (orbit + push-in) is followed with coherent depth-dependent parallax. **The isolated capability sequence is complete.** **M3-A (first integration shot) PARTIAL**: CONTROL PASS on the raw output, APPEARANCE PARTIAL (a finished Blender first frame makes the shot materially more cinematic and the look persists, but the characters still read partly as primitive figures), pre-registered hybrid weapon layer not fully usable (a post-hoc fix works). **SHOWCASE v1** (2026-10-06, not an admission run): the strongest complete video so far (continuous characters, low-key dusk look, 768×448, Blender-owned weapon with geometric ghost repair, ActionTimeline-triggered flash/dust/debris/cracks, graded); it makes no capability claim. **D1 (2026-10-06): autonomous director foundation**: product direction is now prompt -> final video with Blender as an internal engine (ADR-0002); a supported request becomes a validated ShotSpec and CompiledShot, and the Blender scene, controls, first frame, masks and preflight QC are built automatically (executed once from a prompt; LTX not invoked). Showcase v1 is reproduced exactly from its declarative ShotSpec. Rungs 3–6, FLUX.2-klein and Wan2.1-VACE are not run. Session B is **not** started. |
| **Who acts next** | **Owner:** review D1 (`docs/measurements/2026-10-06-d1-autonomous-director-foundation.md`, ADR-0002) and approve the next milestone: the proposed **D2** (one-command prompt -> final video for the Showcase class: orchestrate generation, layer renders, hybrid composite, grade and post-generation QC from the CompiledShot) and/or **M3-B** delivered as a new registry character version. Nothing starts automatically. **No hardware purchases**: the 4070 12 GB, 32 GB RAM and current storage are permanent design constraints. |
| **External spend** | **₹0 of ₹15,000** · active gate: **Gate A (≤ ₹5,000)** · Gate B: locked |
| **Measured results** | **LTX-2.5 22B distilled (INT8 ConvRot) on the RTX 4070 + 32 GB RAM, 512×320×49, 8 steps:** <ul><li>T2V: **cold 31.1 s / warm 7.8 s**.</li><li>First frame + Blender-depth Union control: **cold 32.7 s / warm 8.9 s**.</li><li>Owner review: **R1 pass**; **R2 partial** (motion vague in playback).</li><li>**R2D control diagnostic PASS** (static camera, red box left → right, blue ball approaching, neutral prompt):<ul><li>box centroid within 0.2–2.9 px of Blender ground truth, 99.9 % of travel</li><li>ball area ×6.20 vs ×6.42</li><li>generation 33.1 s</li></ul></li><li>**M2-A representative temple shot PASS** (procedural courtyard, rigid humanoid-shaped proxy moving left → right while approaching, static camera, neutral prompt):<ul><li>98.5 % of travel</li><li>within 0–2.8 px of the reference-tracked path</li><li>area ×1.35 vs ×1.39</li><li>structures stable</li><li>32.3 s</li><li>**caveat:** a small (0.44-cell) secondary figure occluded for about 35 frames re-emerges degraded</li><li>the first frame, not the prompt, sets the character look</li></ul></li><li>**M2-B articulated mace strike PARTIAL** (same temple, static camera, rigged proxy with a fixed root, M2-A prompt unchanged):<ul><li>weapon apex / contact on the authored frames: 0 / 0 frames off (retry +1 / 0)</li><li>excursion 102 % of GT</li><li>body within 2.6 px of GT (no invented translation)</li><li>the arm visibly changes pose through guard → wind-up/apex → strike/contact → recovery</li><li>**but** in the fastest strike frames (76–87 px/frame) the weapon is ghosted/smeared and the shaft vanishes</li><li>the one retry (strike ×1.5 slower, peak 64 px/frame) reduced but did not remove it; the smear follows the fast frames</li><li>`joints.npz` verified in a real scene: projected weapon bone within 0.57 px of the render</li><li>31.7–32.6 s, same memory envelope</li></ul></li><li>**M2-B same-shot 768×448** (original-speed strike, only resolution changed; guide grid 8×5 → 12×7 cells of 64 px; rules pre-registered): **admitted** on the 4070 / 32 GB<ul><li>37.7 s vs 32.6 s; median denoise step 1.00 vs 0.594 s</li><li>peak VRAM 11.9 GB; minimum free RAM 2,058 MB (512: 2,064); commit 75.5 %; pagefile +8 MB</li><li>**NO MATERIAL IMPROVEMENT** for the fast weapon: fast-region retention worst 0.117 (512: 0.009), median 0.568 (0.570); f25 still a ghost; shaft still missing in f25–f27</li><li>timing 0/0 frames, body within 1.9 px, articulation intact; static detail sharper</li><li>the weapon's speed in head widths per frame (1.25) is the same at both sizes, and the whole downswing sits in one 8-frame VAE temporal latent at both (proposed, untested role)</li></ul></li><li>**M2-C authored camera move PASS** (M2-A temple + static rigid proxy; 24° orbit + 7.5 → 6.0 m push-in, raised 3.6 → 3.3 m, fixed 35 mm; M2-A prompt verbatim, no camera words; 512×320×49):<ul><li>three static landmarks at about 8.6 / 10.9 / 15.6 m follow their Blender screen trajectories: direction cos 0.994–0.9998, magnitude 0.90×, ≤ 11.8 px, monotone, no jumps</li><li>parallax ratios reproduced within 0.6 % (normalised 0.457 / 0.692 / 1.0 vs 0.454 / 0.691 / 1.0)</li><li>framing within 7.7 px; push-in area ×1.50 vs ×1.58</li><li>the generated move is ≈ 0.9× the authored one, uniformly across depths</li><li>camera export reproduces the authored `CameraMotion` within 5e-7 m / 3e-5°</li><li>32.4 s; minimum free RAM 2,080 MB; commit 76.2 %; pagefile +50 MB</li></ul></li><li>**M3-A controlled cinematic appearance PARTIAL** (first integration shot: finished-look Blender first frame from `oc_lookdev`, the M2-B strike at original speed, an M2-C-type 24° orbit + 1.4 m push-in, a static ascetic; appearance-only prompt; unchanged model settings; hybrid mace layer + one dust effect composited after; two-axis rules pre-registered):<ul><li>**CONTROL PASS** on the raw output: apex/contact 23/29 = GT (0/0 frames), excursion 1.005, demon within 4.1 px, landmarks cos ≥ 0.993 (magnitude 0.91–0.99), parallax order kept; the arm articulates through every phase</li><li>**APPEARANCE PARTIAL**: materially more finished than M2-B/M2-C (light, haze, materials, design) and it persists f0–f48, but the characters still read partly as primitive figures; LTX keeps the first frame's look but not its fine texture (raw high-frequency detail ≈ the blockout run's)</li><li>the raw fast mace still breaks (f25–27); a matched Blender motion-blur reference shows this is not legitimate blur</li><li>pre-registered hybrid v1 (Blender mace layer over f23–29, holdout occlusion, gain grade, ghost inpainting): solid, attached (grip ≤ 2.9 px) and on time, but over the on-path limit at f25/f27/f28 with a double image; **not fully usable**. Post-hoc v2 is within all limits</li><li>dust effect triggered from the ActionTimeline at the contact frame (f29)</li><li>32.9 s; minimum free RAM 2,070 MB; commit 76.4 %; pagefile +77 MB; no retry</li></ul></li><li>**SHOWCASE v1** (2026-10-06; **a showcase optimisation run, not an admission experiment**: many changes together, no PASS/FAIL): 768×448×49, 8 steps (fixed distilled schedule), seed 1000, one generation of 3 allowed:<ul><li>generation 39.2 s (median step 1.00 s), VRAM 11.9 GB, minimum free RAM 2,064 MB, commit 75.6 %, pagefile +91 MB, gen4 x16 throughout</li><li>the finished first frame's design persisted f0–f48; the fast mace broke again at f25–27 in the raw output and was repaired by the Blender layer (all frames, 90° shutter, holdouts, geometric ghost region + temporal fill)</li><li>colour trackers are not valid under this warm high-contrast grade (stone falls in the gold/crimson ranges); control inputs were validated geometrically (joints 2.1 px, timeline exact, camera 4.8e-7 m)</li></ul></li><li>The depth control is now aligned with the official preprocessing (per-clip min–max disparity, lossless), except for an 8-bit video-input residual.</li><li>The binding resource is **system RAM**: minimum free about 2.0 GB, commit ≤ 75 %, no paging (pagefile ≤ 156 MB).</li><li>VRAM peaks at about 11.9 GB by DynamicVRAM design, with **no sysmem fallback**: R1b, run without it, is byte-identical.</li><li>The PCIe link is Gen4 x16, with a brief gen2 x16 window during weight streaming.</li></ul>Details: `docs/measurements/2026-10-02-ltx25-r1-r2.md`, `2026-10-02-ltx25-r2d-control-diagnostic.md`, `2026-10-02-m2a-temple-shot.md`, `2026-10-03-m2b-temple-strike.md`, `2026-10-03-m2b-resolution-768.md`, `2026-10-03-m2c-camera.md`, `2026-10-03-m3a-controlled-appearance.md` and (showcase, not an admission) `2026-10-03-showcase-v1.md`. Desktop baseline: `2026-10-02-desktop-m1.md` and `2026-10-02-post-update-r1-setup.md`. Mac contract numbers: `docs/contracts.md`. |
| **Primary model** | LTX-2.5 22B distilled + Union IC-LoRA (candidate; confirm/replace via T0 benchmark) |

---

## Ultimatum — the end goal and the hard rules

### End goal (V1 definition of done)

**OneCreations Controlled Cinematics V1:** a local scene-and-shot production system whose first showcase is a
short two-character action sequence with reusable camera motion and timed VFX. V1 is done when **all** of these are true:

1. **One readable parry, one dramatic camera move, one synchronized impact**, delivered as a polished 5–10 s shot through the compositor.
2. **A second version with different characters or surroundings, without rebuilding the action** (same choreography, camera and event timeline).
3. A four-shot miniature sequence (temple reveal, hero close-up, parry/impact, aftermath) sharing design, geography, lighting and damage state.
4. The primary video backend is **chosen by the T0 benchmark** (quality + controllability) and its admission outcome on the 4070 is recorded (A/B/C).
5. **At most one** trained adapter is in use, and only if it beats the same pretrained conditioned graph on held-out shots. Otherwise none.
6. Every accepted shot has a reproducibility record (v1 §29) and passes the hard pass/fail targets (v1 §21).

### Hard rules (non-negotiable)

1. **Budget:** total external compute ≤ **₹15,000**. Until Gate B is unlocked by the owner, cumulative ≤ **₹5,000**.
2. **No paid compute without** (a) `uv run python tools/budget/ledger.py check ...` passing and (b) the owner's explicit go-ahead in that session. Log every rupee in `budget/ledger.csv`.
3. **4070-first:** anything that can realistically be developed, debugged or trained locally is done locally. H100/H200 only for high-value training that can't fit locally (the LTX-2.5 IC-LoRA), and only after G4/G5.
4. **Model choice by quality and controllability**, never by "it fits the 4070". Wan2.1-VACE-1.3B is a local experiment, not the primary.
5. **Don't assume LTX-2.5 fails on 32 GB RAM** — measure the admission ladder. If outcome C, **stop and ask the owner** before any LTX cloud spend.
6. **Honest numbers:** label every figure *measured*, *published*, *arithmetic* or *proposed*. Never invent benchmarks or report only the best seed.
7. **Rights:** no Mixamo output in any training/testing corpus; license snapshot for every model and asset; no Hunyuan/H3 outputs as training targets.
8. **The Blender path always delivers.** No neural component may become the only route to a finished shot.
9. **Git hygiene:** no weights, datasets, renders or caches in Git (see `.gitignore`). Pin upstream repos to commits.
10. **Authorship:** commits and docs are by Harshavardhan M (GitHub `harsha135135`) only. No AI co-author lines or "generated with" attributions anywhere.

---

## Milestones and gates

Gates are defined in `docs/decisions/ADR-0001-hardware-and-compute-strategy.md`.

| # | Milestone | Where | Exit / gate | Status |
|---|---|---|---|---|
| M0 | Research snapshot, ADR, runbooks, tooling, registry, budget ledger, tests | Mac | Repo pushed; tests pass on Mac | ✅ **Done** 2026-10-02 |
| M0.5 | Session A (Mac): contracts + schemas, exact time base/TimeWarp, camera geometry, trajectory library (stats, normalize, retarget + clearance, CSV, minimal COLMAP), shot validator, cache keys, Blender exporter/importer/visualizer + diagnostic scene, CLI, 107 tests | Mac | `uv run pytest -q` passes incl. 11 headless-Blender tests | ✅ **Done** 2026-10-02 |
| M1 | Desktop setup: clone, `uv sync`, iGPU display, Blender 4.5 LTS, baseline measurements. Owner decisions: sysmem fallback, pagefile and Defender tuning wait for a measured need in M3; pinned ComfyUI moves to M3 | Desktop | **G0:** `tools/windows/check_env.ps1` clean, idle VRAM ≈ 0, `uv run pytest -q` passes (incl. `-m blender` on Windows Blender 4.5) | ✅ **Done** 2026-10-02. G0 passed: check_env exit 0 with 0 FAIL and 3 accepted WARN; idle VRAM 129 MiB; 107 tests pass including 11 Blender. Evidence: `docs/measurements/2026-10-02-desktop-m1.md` |
| M1.x | **Storage efficiency policy.** Owner decision 2026-10-02: **no hardware purchases**, so the current storage is permanent. G: has 239.16 GiB free.<ul><li>Keep only model files the active path needs, with staged downloads.</li><li>No duplicate variants or weights.</li><li>Clean superseded renders and caches only with owner approval.</li></ul> | Owner + desktop | Applied each session (free space recorded before and after) | 🟢 Policy in force. The 4 LTX files (36.3 GiB) are all pinned and used. About 4.2 GiB is safely reclaimable on G: (uv wheel cache), pending owner approval |
| M2 | Use the Session A exporter on the first real scene (V0 rigs + environment); extend the diagnostic checks only where the real scene needs it (pose visibility, Cryptomatte if compositing requires it) | Desktop | **G1:** Windows Blender tests pass + a real-scene export bundle validates | 🟡 **In progress.** **M2-A ✅ PASS** (2026-10-02): a representative temple scene exported and validated through the Session A exporter, with rigid-translation control followed (`docs/measurements/2026-10-02-m2a-temple-shot.md`). **M2-B 🟡 PARTIAL** (2026-10-03): first rigged actor and first real use of the armature/joint export and `ActionTimeline`; strike timing followed to the frame, but the fast weapon smears (`docs/measurements/2026-10-03-m2b-temple-strike.md`). **M2-B @ 768×448** (2026-10-03): admitted; no material improvement for the fast weapon (`…/2026-10-03-m2b-resolution-768.md`). **M2-C ✅ PASS** (2026-10-03): authored camera move with coherent parallax; first real-scene `CameraMotion` import → export round trip (`…/2026-10-03-m2c-camera.md`). **Isolated capability tests are complete.** The first combined shot ran as **M3-A** (2026-10-03, PARTIAL; see M3) |
| M3 | Admission ladders: LTX-2.5 (INT8 ConvRot + offload), FLUX.2-klein-4B, Wan2.1-VACE-1.3B | Desktop | **G2:** outcome A/B/C recorded for each in `admission_records/` + `model_registry/models.yaml` | 🟡 **In progress.** LTX-2.5 **R1 (T2V) and R2 (first frame + depth Union) run reliably** at 512×320×49 (owner: R1 pass, R2 partial). The **R2D control diagnostic passed**: the Union depth control is clearly followed (2026-10-02; `docs/measurements/2026-10-02-ltx25-r1-r2.md`, `…-r2d-control-diagnostic.md`). **M3-A integration shot 🟡 PARTIAL** (2026-10-03): CONTROL PASS, APPEARANCE PARTIAL, pre-registered hybrid weapon layer not fully usable (`docs/measurements/2026-10-03-m3a-controlled-appearance.md`). Not yet run: LTX rungs 3–6, FLUX.2-klein, Wan2.1-VACE. No A/B/C outcome yet |
| M4 | V0 shot in Blender only: two rigs, one environment, one parry, one dive/orbit, one timed effect | Desktop | Deterministic preview correct (parallel with M3) | ⬜ |
| M5 | T0 pretrained baseline on the 12-shot benchmark (staged) | Desktop | **G3:** primary confirmed/replaced; a named, learnable defect (or "no training needed") | ⬜ |
| M6 | Local training: T1 FLUX.2-klein LoRA (if G3 justifies), VACE-1.3B rehearsal; LTX dataset + caches + config prepared and validated | Desktop | **G4:** local train→reload→deploy→eval loop works; LTX outcome A/B | ⬜ |
| M7 | H100 admission (≤ 2 h) then Gate A pilot (≤ 8 H100 h total) | Cloud | **G5** then pilot result vs pretrained | ⬜ Locked (needs G4 + owner go-ahead) |
| M8 | Gate B decision | Owner | **G6:** pilot beats pretrained + owner approves → up to ₹15,000 total | ⬜ Locked |
| M9 | V1 four-shot sequence + alternate-asset version + evaluation report | Desktop | V1 definition of done (above) | ⬜ |

---

## What exists in the repo now

| Path | What it is | State |
|---|---|---|
| `docs/research/2026-10-01-decision-v1.md` | Original research/design document (verbatim snapshot) | Reference |
| `docs/decisions/ADR-0001-...md` | Hardware/compute strategy; overrides v1 where they conflict | Accepted |
| `docs/runbooks/windows-desktop-setup.md` | M1 step-by-step | Executed 2026-10-02; owner deferrals recorded in §1 |
| `docs/measurements/2026-10-02-desktop-m1.md` (+ PCIe CSVs) | Desktop baseline: versions, VRAM before/after the iGPU move, memory/commit/pagefile, PCIe under load, storage, check_env | Measured |
| `docs/runbooks/admission-ladder.md` | M3 procedure + record format + results table | R1/R2 rows filled 2026-10-02 |
| `docs/measurements/2026-10-02-post-update-r1-setup.md`, `2026-10-02-ltx25-r1-r2.md` | Post-update verification, driver 591.86, Smart App Control, ComfyUI pins, staged downloads; LTX-2.5 R1/R2 results and bottleneck analysis | Measured |
| `tools/admission/comfy_run.py`, `make_controls.py`, `tools/windows/oc_env.ps1` | ComfyUI job runner with per-phase timings; Blender depth → control video; session-only data/cache environment | Used for R1/R2; unit-tested |
| `integrations/blender/build_control_diagnostic_scene.py`, `tools/admission/control_diagnostic.py` | R2D diagnostic scene (static camera, box L→R, ball toward camera); control inspection + objective comparison, **spec-driven since M2-A** (ground truth, coverage in guide cells, control contrast, occlusion, colour tracking, pre-registered checks, report-only structure drift, contact sheets). **Since M2-B:** `gold` colour rule, `timing` (apex/contact frames) and `position` (stationary root) checks, per-subject gate options, joint-projection and ActionTimeline-agreement cross-checks, event contact sheet | Used for R2D, M2-A, M2-B; unit-tested |
| `integrations/blender/build_temple_shot_scene.py`, `tools/admission/experiment_keys.py`, `tools/windows/run_admission.ps1` | M2-A representative temple scene (procedural; rigid humanoid-shaped proxy; spec with pre-registered tracking/gate); run cache keys via `cachekeys`; reproducible run launcher (records input hashes) | Used for M2-A; tested (scene: build + export validated) |
| `integrations/blender/build_temple_strike_scene.py`, `render_reference.py` | M2-B scene: the M2-A temple (shared builders) + a rigidly skinned 16-bone humanoid proxy with a fixed root and one IK-posed mace strike, written as an `ActionTimeline`; `--strike-frames`. Reproducible Cycles OptiX beauty reference (first frame + lossless preview + hash sidecar) | Used for M2-B; Blender-tested |
| `integrations/blender/build_temple_camera_scene.py` | M2-C scene: the M2-A temple + static rigid proxy; colour-banner parallax landmarks; one authored `CameraMotion` (orbit + push-in, look-at with a yaw framing offset, fixed lens) keyed by `oc_import_camera`; exact per-frame clearance and AABB proxies in the spec | Used for M2-C; Blender-tested |
| `integrations/blender/build_temple_action_scene.py`, `oc_lookdev.py`, `render_layers.py` | M3-A scene: the M2-A temple finished with procedural PBR materials, dusk world, bounded haze, three-point light and AgX (`oc_lookdev`); the M2-B rig and strike on a finished demon; a static ascetic; an M2-C-type `CameraMotion`; a deterministic dust effect in an excluded collection; the spec's `layers` (`CompositeManifest`). `render_layers.py` renders a layer with holdouts, transparent film and motion blur; `render_reference.py --motion-blur` renders the matched blur reference | Used for M3-A; Blender-tested |
| `integrations/blender/build_showcase_scene.py`, `oc_characters.py`, `render_stills.py` | SHOWCASE v1 scene: continuous characters (metaball anatomy → smooth mesh, swept tubes, armour shells, cloth panels, rest-space chain weights) on the unchanged M2-B rig; upgraded temple; low-key dusk look; deterministic dust/debris/sparks/cracks and a light-only flash. `render_stills.py`: look-development stills | Used for the showcase; Blender-tested |
| `src/onecreations/director/`, `library/registry.yaml`, `contracts/director.py`, `contracts/registry.py` | D1 director: asset registry (18 real entries), action events, camera presets + envelope, processing-policy rules, ShotSpec validation, compiler (ShotSpec -> CompiledShot), keyword_v1 prompt interpreter (replaceable), planner, QC as data + preflight evaluator, dry-run / preflight executor; CLI `onecreations director ...` and `onecreations generate ... --dry-run / --preflight` | Used for D1; unit- and Blender-tested |
| `tools/admission/finish_grade.py`, `progress_sheet.py` | Reproducible finishing grade (eq, colour balance, vignette, sharpen, fixed-seed grain, post-only shake; sidecar with the filter chain) and labelled progress contact sheets across clips of any size | Used for the showcase; unit-tested |
| `tools/admission/hybrid_composite.py` | Minimal hybrid compositor: protected frames from the authored speed and raw retention, per-channel gain, ghost inpainting (v1; `--ghost-under-layer` = v2), alpha-over of holdout layers, effects at their ActionTimeline trigger, A/B/C sheets, per-frame report | Used for M3-A; unit-tested |
| `tools/admission/resolution_compare.py` | Same-shot comparison across output sizes: Union guide grid, weapon size and motion in px and guide cells, projected weapon-arm chain, per-frame generated/reference retention | Used for M2-B 768×448; unit-tested |
| `workflows/ltx25/` | API-format R1 (T2V video-only) and R2 (first frame + depth Union) workflows, plus R2D, M2-A, M2-B, M2-B 768×448, M2-C and M3-A variants, with deviations from the official graphs documented | Used for R1–M3-A |
| `admission_records/` | `records.jsonl` (+ per-run CSV, comfy reports, specs, inspect/compare JSON, cache keys) for ltx25-r1a, r1b, r2, r2d, m2a-temple, m2b-strike, m2b-strike-retry, m2b-strike-768, m2c-camera, m3a-action (+ M3-A layer, composite and appearance reports) | Measured |
| `docs/runbooks/local-training.md` | M6 procedure (T1, VACE-1.3B, LTX prep) | Ready; trainer commits to pin |
| `docs/runbooks/cloud-h100.md` | M7 procedure, cost controls | Ready; locked behind G4 |
| `tools/windows/check_env.ps1` | Read-only environment check (G0); default data root `G:\onecreations` | Run on Windows 2026-10-02: 0 FAIL, 3 WARN |
| `tools/admission/monitor.py` | Runs a command, samples GPU/RAM/pagefile/**commit**/**PCIe gen-width** (start, under load, end), writes CSV + JSONL summary | Used for R1/R2 on real GPU jobs |
| `tools/inspect_safetensors.py` | Header-only tensor/LoRA-rank inspector (no weight load) | Tested on Mac with synthetic file |
| `tools/registry/hash_files.py` | Streaming SHA-256 for model files → registry | Tested on Mac |
| `tools/budget/ledger.py` + `budget/` | Spend ledger with gate enforcement | Tested on Mac |
| `model_registry/models.yaml` + `licenses/` | Candidate models, roles, licenses, admission status | LTX-2.5 R1 files and Union LoRA hashed (== HF LFS); ComfyUI, LTXVideo and Blender pinned; license snapshots stored; other models TODO |
| `training/**/experiment-card*.yaml` | Experiment cards for T1, VACE-1.3B, LTX T2 (not trainer-native configs) | Proposed; trainer configs to be derived from pinned upstream examples |
| `docs/contracts.md` | Conventions, contracts, issue codes, cache-key graph, export bundle format, Mac measurements, deferred list | Reference |
| `src/onecreations/contracts/` + `schemas/` | Pydantic contracts: Project, CharacterAsset, CameraMotion, ActionTimeline, TimeWarp, VFXEvent, Shot, ModelBackend, ExperimentRecord, AdmissionRecord, ExportManifest, CompositeManifest (M3-A); generated JSON Schemas | Tested on Mac |
| `src/onecreations/timebase.py` | Exact rational time, frame rates (incl. 24000/1001), TimeWarp with holds | Tested; shared with Blender scripts |
| `src/onecreations/geometry/` | Quaternions, Blender↔OpenCV conventions, rigid validation, Blender intrinsics → K, projection | Tested; verified against Blender 4.5 |
| `src/onecreations/camera/` | Trajectories (spline/slerp), stats, normalize (up/scale/provenance), retarget + clearance report, CSV, minimal COLMAP import | Tested on Mac |
| `src/onecreations/shotpkg/` | Project loader + shot cross-reference validator + event schedule | Tested on Mac |
| `src/onecreations/cachekeys.py`, `hashing.py` | Canonical JSON, content/array digests, artifact dependency graph | Tested on Mac |
| `src/onecreations/blender_bridge.py`, `blender_bundle.py` | Find/run Blender headless; load + verify export bundles | Tested on Mac and Windows (Blender 4.5.14) |
| `integrations/blender/` | `build_diagnostic_scene.py`, `oc_export.py`, `oc_import_camera.py`, `oc_visualize_trajectory.py` | Tested on Mac and Windows; numbers agree (see `docs/contracts.md`) |
| `examples/diagnostic/` | Fixture project from v1's own numbers (contact 0.90 s, 6 s shot, impact hold); backend profile is a labelled test fixture | Validates (2 expected warnings) on both machines |

All tests pass on the Windows desktop: 107 at M1, 117 with the admission tooling, 120 with the R2D control-diagnostic tooling, 124 at M2-A, 132 at M2-B, 135 after the 768×448 comparison, 142 at M2-C, 152 at M3-A, 162 after SHOWCASE v1, **180** at D1 (Python 3.12.6 via uv 0.12.22).

**Not started:** Session B (VFX event system, dataset/provenance pipeline, 12-shot evaluation framework), ComfyUI workflow templates, studio UI, job queue. Deferred Session A items are listed in `docs/contracts.md` (Cryptomatte decoding, beauty renders, motion vectors, joint visibility, sub-frame pass rendering, auto path adjustment, COLMAP distortion/gyro, visualizer preview renders).

### Next on the desktop (owner decides the order)

1. **Isolated capability sequence complete:** R2D PASS · M2-A PASS · M2-B PARTIAL (articulation and timing work; the fast thin weapon smears) · 768×448 no material improvement · **M2-C PASS**. Designs: `docs/measurements/2026-10-03-m2c-camera.md` §17.
   - **M3-A (first integration shot) done 2026-10-03: PARTIAL.** CONTROL PASS, APPEARANCE PARTIAL, pre-registered hybrid v1 not fully usable. See `docs/measurements/2026-10-03-m3a-controlled-appearance.md`.
   - **Proposed next: M3-B** (owner to approve; not started), on the same M3-A shot, controls, timeline and configuration:
     - upgrade the first frame's characters in Blender: continuous sculpted body meshes and costume detail on the same rig and silhouettes, so the control stays valid
     - pre-register the hybrid v2 ghost rule (inpaint raw remnants under the layer's partial alpha) and validate it
     - add an actor-in-front-of-weapon occlusion case if the choreography allows
     - one generation, at most one evidence-driven retry
     - a local image-model route for the first frame stays an owner decision (no automatic download)
   - **After an APPEARANCE PASS with usable hybrid protection:** the two-character parry.
   - **Resolution:** 512×320 is the admitted capability baseline. 768×448 is a quality option (admitted, +16 % time, same RAM).
   - **Fast weapon-critical frames:** deterministic Blender geometry/compositing is the candidate route (hard rule 8; joints and timing are exact). It is part of the intended hybrid architecture, proposed and not built.
   - **Not planned:** a speed sweep, another resolution, temporal-latent alignment tests, more steps, guide-strength changes. Each needs an owner decision.
   - No 960×544 or upscaler.
   - **Working heuristics (proposed, not proven rules):**
     - control-relevant subjects should span ≥ about 2 Union-guide cells (64 px each at 512×320)
     - avoid long occlusions of small secondary subjects, or composite them from the Blender beauty pass
     - the first frame sets the look
     - camera moves (M2-C, 1 run): place parallax landmarks where they stay clear of the subject for the whole move (probe visibility first); expect the generated move to reach about 0.9× the authored displacement
     - fast weapon frames (local working hypothesis from 2 speeds at 512 plus one 768 run; not a model limit): the weapon smeared in its fastest frames at 512×320, and 768×448 did not change that at equal speed in head widths per frame; contact and hold frames render solidly
     - finished looks (M3-A, 1 run): LTX keeps the first frame's light, colour, materials and design through motion but not its fine texture, and adds no realism, so the first frame is the appearance ceiling
     - fast-weapon frames: protect them with the Blender layer (holdout occlusion, matched 180° blur) and measure against the blur-matched reference, not the sharp one
     - finished looks need colour rules validated on the finished reference before the run
2. **LTX rung 3** (orbit, fast near pass, two-character motion) builds on M2/V0 scenes. **Rung 6** is reliability: 3 runs from a clean launch, plus an oversized request and recovery.
3. **FLUX.2-klein-4B and Wan2.1-VACE-1.3B ladders** come later, with staged downloads within the storage policy.
4. **Before every run:**
   - Updates are paused (until 2026-10-09; re-pause after that).
   - Dot-source `tools\windows\oc_env.ps1`. Close browsers: RAM is the binding resource.
   - Launch runs with `tools\windows\run_admission.ps1`. Gate and compare with `control_diagnostic.py --spec`; cache keys come from `experiment_keys.py`.
   - The NVIDIA program entry for the ComfyUI interpreter exists at *Use global setting*.

### Done from the M1 handoff list (kept for reference)

1. **Storage plan (owner).** The data root is `G:\onecreations\`, a temporary choice with 280 GB free on one 1 TB NVMe (C:, F: and G: share it). Settle this before downloading any weights, datasets or caches.
2. **Windows Update.** About 11 GB of updates were downloaded on 2026-10-02, and the last installed hotfix is from 2026-02. Let it install, or pause updates, before any multi-hour run.
3. **PCIe link.** Before the reboot it ran Gen4 x4 under load; after the reboot it ran Gen4 x16, with the cause unidentified. Check `nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.width.current --format=csv` before each admission run. Extend `tools/admission/monitor.py` to record link gen/width before M3 rungs. Make no BIOS PCIe changes without the owner.
4. **Deferred tuning.** Apply each item only when an M3 admission run measures the need:
   - sysmem fallback per executable/profile, never global
   - the pagefile, for a measured commit/paging shortfall
   - Defender, as the narrowest data/cache path
5. **M2:** export a first real scene with the Session A exporter. **M3:** clone ComfyUI and ComfyUI-LTXVideo into `G:\onecreations\upstream` pinned to commits, then run the admission ladders (`docs/runbooks/admission-ladder.md`).

---

## Open questions for the owner

1. If LTX-2.5 admission is **outcome C**: approve a ≤ 2 h H100 cloud T0 comparison (≤ ₹710)? Or promote the best admitted challenger? (Decide when M3 finishes.)
2. Gate B unlock after the pilot (M8).
3. ~~Where the desktop keeps big data~~ → `G:\onecreations\`. **No hardware purchases**: no new SSD, RAM or GPU. Open: approve reclaiming the G: uv wheel cache (4.16 GiB; only needed for an offline rebuild of the ComfyUI env)? The C: pip cache (7.99 GiB) is the owner's own, pre-existing, and out of this project's scope.
4. When to run Session B (VFX events, dataset/provenance, evaluation framework): on the Mac now, or after the first GPU measurements. Not started automatically.
5. PCIe x4 → x16: should the earlier x4 be investigated physically (reseat the card, check for a riser), or only monitored? No BIOS or hardware changes have been made.
   x4 has **not** recurred: Gen4 x16 held under load in every run since. The monitor now flags it automatically.
6. **Quality ladder:** ~~same-shot 768×448~~ → done 2026-10-03. It is admitted (RAM unchanged, +16 % time) and gives sharper static detail, but no material improvement for the fast weapon. M2-C ran at 512×320. Open: should the combined action shot use 768×448? 960×544 and the official upscaler (1 GB) stay deferred.
7. **Smart App Control** is off (owner, 2026-10-02), because it blocked PyAV's unsigned DLL. Keep it off on this ML workstation?
8. ~~Next M2 experiment~~ → M2-C done 2026-10-03 (PASS). No further isolated M2 axis is planned.
9. **M2-B fast-weapon smear:** (a) 768×448 has been run; there was no material improvement. Remaining routes:
   - plan to composite weapon-critical fast frames from Blender (the candidate; not built)
   - a speed sweep (not planned)
   - a test of the proposed temporal-latent hypothesis (not planned)

   Optional: a playback verdict on the M2-B clips (512, retry, 768), recorded separately from the classifications.
10. **First combined representative action shot:**
    - choose the action (for example a strike against a second proxy or object) and the camera move
    - decide whether weapon-critical fast frames are Blender-composited from the start
    - choose the resolution (512 or 768)

    Nothing starts automatically. Optional: a playback verdict on the M2-C clip.

    → Done as **M3-A** (2026-10-03): the M2-B strike at original speed, an M2-C-type move, a static defender, Blender-composited weapon frames from the start, 512×320. Result PARTIAL.
11. **M3-B (proposed):**
    - approve the Blender character upgrade + pre-registered hybrid v2 on the M3-A shot
    - or say whether a local image model should produce the finished first frame (needs a download and a new, non-exact alignment gate)
    - optional: playback verdicts on the M3-A clips (raw `ltx25_m3a_00001_.mp4`, `analysis/hybrid/hybrid.mp4`, `analysis/hybrid_v2/hybrid.mp4`), recorded separately from the classification

---

## How to update this file

At the end of every session on any machine:

1. Update the header table (date, phase, who acts next, spend, measured results).
2. Tick milestones; paste the outcome and the path of the evidence (admission record, eval report).
3. Add a line to the **Session log** (newest first). Keep it factual: what was done, what was measured, what failed.
4. Commit with a plain message, e.g. `status: M3 LTX-2.5 ladder rungs 1-3 measured`, and push.

## Session log

- **2026-10-06 (night) · Windows desktop (D1: autonomous director foundation)**
  - **Owner direction:** the product is prompt -> final video; Blender becomes internal infrastructure (ADR-0002). D1 makes the Showcase shot class constructible from a structured spec, with natural-language planning on top. No LTX run, no cloud, no training, no downloads.
  - **Built:**
    - contracts DirectorPlan / ShotSpec / CompiledShot / AssetRegistry (separate layers; semantic ids; events as `action.EVENT`)
    - `library/registry.yaml` (18 real entries with provenance and limitations)
    - `onecreations.director` (registry, actions, camera, policies, validate, compiler, prompt, interpreter keyword_v1, planner, qc, executor)
    - CLI `director` and `generate --dry-run / --preflight`
    - `build_showcase_scene.py --config` (compiled scene build; per-component effects with unchanged seeded draws)
  - **Showcase v1 reproduction:** `examples/director/showcase_v1.shotspec.json` compiles to the archived layers, timeline, placements, look, camera move (49 samples, 0.0 m), grade and a byte-identical LTX workflow and prompt; the Blender build from the compiled config equals the hand-configured build; the exported camera, object and joint digests equal the Showcase generation export. The Showcase-session re-export check had been vacuous (compared missing keys); redone properly, it holds.
  - **CONTACT propagation:** strike_frames 8 -> CONTACT 31 everywhere (layers, duration, jolt; Blender agrees).
  - **Prompt -> Blender preflight executed once (47 s):** all 10 preflight QC checks pass (weapon bone 2.11 px, camera 4.7e-7 m, clearance 1.95 m, 14 isolated background px); first frame, depth control and 12 semantic masks on G:.
  - **Tests and storage:** +18 tests; 180 pass; 4 new schemas. G: 237.76 -> 237.50 GiB. ₹0 spent.
- **2026-10-03 → 2026-10-06 · Windows desktop (SHOWCASE v1: best controlled cinematic shot today; NOT an admission experiment)**
  - **Owner brief:** pause the admission roadmap and produce one showcase-quality shot with everything available locally: joint optimisation allowed, ₹0, no downloads, no training, no cloud, at most 3 generations, no seed shopping.
  - **Before generation:**
    - ranked M3-A weaknesses (toy-mannequin characters, flat bright look, diagnostic composition, demon facing the camera, fast weapon, plain temple, small impact)
    - new `oc_characters.py` (continuous metaball bodies, swept tubes, shells, cloth panels, chain weights; demon 98,347 vertices, 0 unweighted); demon on the unchanged M2-B rig and keys, yawed 30° toward the defender; static ascetic in a forward trident guard
    - low-key dusk contre-jour lookdev, braziers, a lit sanctum doorway, shikhara, oxblood banners (diagnostic banners removed); three look rounds
    - 768×448 (aspect 1.714) with a recomposed M2-C-family move (24° orbit, 7.6 → 6.3 m push-in, 2.25 → 1.95 m, 32 mm); 1024-sample first frame
    - exporter: `oc_exclude_from_passes` flag (flames) → clean depth
    - 8 steps kept (the model card specifies a fixed 8-step distilled schedule); seed 1000; no upscaler installed
  - **Generation:** one (`showcase-v1-run1`, 39.2 s; records in `admission_records/showcase/`). The owner closed Chrome first. No second run: no correctable generation issue.
  - **After generation (post-hoc, allowed for a showcase):**
    - weapon owned by Blender in all frames at a 90° shutter, holdout occlusion, gain grade, 0.7 px soften
    - new geometric `swept_band` ghost region with a per-pixel temporal fill (colour cannot see the weapon in this grade)
    - ActionTimeline-triggered dust volumes, debris, sparks, cracks and an additive light-only flash (dust and flash revised after viewing)
    - restrained reproducible grade with a 2-px post-only impact jolt
  - **New contract fields:** `CompositeManifest` (include_frames, ghost_mode swept_band, ghost_fill, ghost_band_px, ghost_keep_objects, ghost_colors, blend add, soften_px, light_only); `ExportPasses.excluded_objects`. M3-A composite reproduces identically. +10 tests; 162 pass.
  - **Result:** SHOWCASE RESULT, the strongest complete video so far. Remaining: stylised CG characters (the first frame is the appearance ceiling), LTX softness, a splashy f26 head, static defender.
  - **Note:** a `checkpoint before cloud task` commit (`75e3236`) appeared on main during the session with an intermediate snapshot; the final work is committed on top.
  - **Storage:** G: 238.76 → 237.77 GiB; no downloads. ₹0 spent.
- **2026-10-03 (late evening) · Windows desktop (M3-A: controlled cinematic appearance → PARTIAL)**
  - **Owner brief:** the first integration shot: authored control + generative appearance + deterministic protection.
    - 512×320 × 49, unchanged model settings, an appearance-only prompt
    - a finished aligned first frame, the M2-B strike, an M2-C-type move, a simple defender
    - a minimal hybrid weapon layer, one ActionTimeline-triggered effect
    - two-axis pre-registered classification; one generation + at most one retry; ₹0
  - **Review claims verified** against records: 49 frames / 24 fps / 2.04 s, 8 steps; R1 more cinematic than the M2 blockouts; the M2-B smear is concentrated in the fastest frames; 768 no fix. No local image model exists (`models/flux`, `models/wan` empty), so the first frame is a finished Blender render (route A).
  - **New:**
    - `oc_lookdev.py` (procedural PBR, dusk world, bounded haze box, three-point light, AgX High Contrast)
    - `build_temple_action_scene.py`, `render_layers.py`, `render_reference.py --motion-blur`
    - `CompositeManifest` contract + schema; `hybrid_composite.py`
    - `oc_export` hides volume-only helpers in the passes (`passes.excluded_volume_objects`)
    - colour rules `crimson` / `gold_deep` / `teal`
    - fixed a rig-name shadowing bug in `build_rig`
    - +10 tests; 152 pass
  - **Gate passed:** first frame = reference f0 bit-exact; joints 0.62 px; timeline 23/29 exact; camera 4.6e-7 m; clearance 3.3 m; trackers reproduce GT. Before generation: the haze speckle in the passes was fixed, the banners were moved, `approach` was dropped for the armoured demon, and the hybrid on-path criterion was recalibrated by a dry run on the blur reference.
  - **`ltx25-m3a-action`:**
    - **CONTROL PASS** (timing 0/0, demon within 4.1 px, landmarks cos ≥ 0.993, parallax order)
    - **APPEARANCE PARTIAL** (materially more finished and persistent; characters still partly primitive; fine texture lost)
    - raw mace blob f25–27 (not legitimate blur)
    - hybrid v1 not fully usable (on-path over limit at f25/f27/f28, double image); post-hoc v2 within limits
    - dust at f29
    - 32.9 s; VRAM 11.9 GB; minimum free RAM 2,070 MB; commit 76.4 %; pagefile +77 MB
    - no retry: no single generation-fixable cause
  - **Conclusion:** training not justified. Proposed next: M3-B (first-frame character upgrade + pre-registered hybrid v2) before the parry; not started.
  - **Storage:** G: 238.97 → 238.76 GiB; renders 234 MB; no downloads. ₹0 spent.
- **2026-10-03 (evening) · Windows desktop (M2-C: authored camera move → PASS)**
  - **Owner brief:** the final isolated capability test is static → moving camera. 512×320 baseline, one generation, at most one retry, no camera words in the prompt, image-space evidence only, rules pre-registered.
  - **Design (before generation):**
    - static M2-A proxy at (+2, −3.5); option B, subject static
    - a 24° orbit plus a 7.5 → 6.0 m push-in from 3.6 → 3.3 m height, fixed 35 mm
    - look-at with a 12° yaw framing offset (actor held in the right third); path 3.22 m, peak 2.07 m/s, peak 15.4°/s, roll 0
    - authored with `look_at` → `CameraTrajectory` → `CameraMotion`, keyed by `oc_import_camera`
    - landmarks chosen from per-frame ray-cast probes: green / magenta / cyan banners on the left colonnade at about 8.6 / 10.9 / 15.6 m
    - two earlier layouts were rejected before the gate (the far layer passed behind the actor; a shadowed shrine-tower banner sat below the cyan rule)
  - **New:**
    - `build_temple_camera_scene.py`
    - `control_diagnostic.py`: `trajectory`, `parallax`, camera contract, clearance, visible-area gate, occlusion/reveal timeline, landmark colour rules
    - +7 tests; 142 pass
  - **Gate passed:**
    - camera contract 4.8e-7 m / 2.6e-5°
    - clearance 3.3 m (floor), objects ≥ 5.7 m, `clearance_report` ok
    - parallax signal 52 / 79 / 115 px
    - trackers reproduce GT within 0.9 px
    - far banner revealed from behind the third pillar in f0–11
  - **`ltx25-m2c-camera`:**
    - metric and visual **PASS**: cos 0.994–0.9998, 0.90× at all depths, ≤ 11.8 px, monotone, no jumps
    - parallax normalised 0.457 / 0.692 / 1.0 vs 0.454 / 0.691 / 1.0
    - framing within 7.7 px; early reveal agrees
    - the late far-banner tracked-area dips are colour drift, not occlusion
    - 32.4 s; VRAM 11.9 GB; minimum free RAM 2,080 MB; commit 76.2 %; pagefile +50 MB
    - no retry (rule)
  - **Conclusion:** the isolated capability sequence is complete. The next milestone is the first combined representative action shot; not started.
  - **Storage:** G: 239.03 → 238.99 GiB, with no downloads. ₹0 spent.

- **2026-10-03 (later) · Windows desktop (M2-B same-shot 768×448 → admitted, NO MATERIAL IMPROVEMENT)**
  - **Owner brief:** one isolated resolution comparison, using the original-speed M2-B strike at 512×320 vs 768×448. One generation. No M2-C, no speed sweep, no system tweaks. Report px and guide cells. Pre-register the comparison.
  - **Isolation:**
    - `--resolution` is new in the scene builders; defaults reproduce run 1 and M2-A exactly
    - the 768 spec differs from run 1's only in `resolution`; the ActionTimeline is identical
    - the 768 workflow differs only in `EmptyLTXVLatentVideo` width/height and the output prefix
    - consequences, documented: the aspect ratio goes 1.6 → 1.714 with the horizontal FOV kept (a 16 px top/bottom trim, no subject cropping); the official tiled decode now tiles; depth normalisation is unchanged
  - **Control grid** (derived from the pinned `iclora.py` and `nodes_lt.py`): latent 16×10 → 24×14; guide 256×160 → 384×224 = 8×5 → 12×7 cells, 64 output px per cell at both sizes
  - **Mace geometry:**
    - head 0.84–1.17 → 1.28–1.75 cells
    - peak 80 px = 1.25 cells/frame → 120 px = 1.87 cells/frame, which is 1.25 head widths per frame at both
  - **New:** `tools/admission/resolution_compare.py` (+3 tests; 135 pass)
  - **Pre-registration:** `…_ltx25-m2b-strike-768_preregistration.json`, written before the run
  - **Gate passed on the first attempt:** joints max 0.79 px, events 23/29 = timeline, trackers reproduce GT, in frame
  - **Resource baseline:** 23.62 GB free, commit 16.3 %, pagefile 154 MB used, GPU idle, Chrome/Edge closed, no system changes
  - **`ltx25-m2b-strike-768`** (one generation):
    - 37.7 s (median step 1.00 s); VRAM 11.9 GB; minimum free RAM 2,058 MB; commit 75.5 %; pagefile +8 MB; gen4 x16 (one gen2 sample) → **admitted**
    - timing 0/0 frames; excursion 99.3 %; body within 1.9 px; arm articulation intact; static detail sharper (PSNR vs own reference 28.6 vs 27.6 dB)
    - fast-region retention worst 0.117 (512: 0.009), median 0.568 (0.570); f25 still a ghost; shaft absent f25–26, partial stub f27
    - pre-registered class: **NO MATERIAL IMPROVEMENT**
  - **Conclusion (conservative):** this strengthens, but does not prove, that the fast-weapon limitation is temporal/generative rather than spatial. Next: M2-C. Weapon-critical fast frames go to the Blender-compositing candidate.
  - **Storage:** G: 239.08 → 239.03 GiB, with no downloads. ₹0 spent.

- **2026-10-03 · Windows desktop (M2-B: articulated mace strike → PARTIAL, run + one retry)**
  - **Owner decisions this session:**
    - M2-B is next.
    - PASS additionally requires coherent weapon-side arm articulation: the arm visibly changes pose through every phase, with no independent mace, no material smear or ghosting of the limb, and no actor translation. This is a visual/contact-sheet criterion.
    - An owner playback verdict is not a blocking dependency for classification.
  - **Scope:** one axis from M2-A, rigid → articulated. The temple, static camera, 512×320×49, graph, seed and **prompt** are unchanged. The actor's root and legs are never keyed.
  - **Refactor:** `build_temple_shot_scene.py` became reusable builders, verified neutral:
    - the rebuilt M2-A spec is identical; depth and object index are bit-identical
    - only normal-pass float noise (≤ 1.5e-5) changes the bundle hash, the same as rebuilding with the pre-refactor script
    - re-exporting the saved `.blend` is bit-identical
  - **New:**
    - `build_temple_strike_scene.py`: a rigidly skinned 16-bone proxy; a gold mace head (the only gold in the scene); IK-solved FK keys for guard → wind-up → apex f24 → strike → contact f30 → hold → recovery; an `ActionTimeline`
    - `render_reference.py`: Cycles OptiX, 64 spp, lossless preview, hash sidecar
    - `control_diagnostic.py`: `gold`, `timing`, `position`, per-subject gate options, joint/timeline cross-checks, event sheet
    - 132 tests pass
  - **Pre-LTX gate passed:**
    - head 0.9–1.0 cells; excursion 3.47 cells; contrast ≥ 0.16 on every frame
    - joint projection vs render: max 0.57 px
    - stationary bones 0.0 m
    - exported events = ActionTimeline (0 / 0 frames)
  - **`ltx25-m2b-strike`:**
    - metric PASS: apex/contact 0/0 frames off GT, excursion 102 %, body within 2.6 px
    - the arm follows every phase
    - **but** the weapon is ghosted at f25 (gold area 0.9 % of the reference), smeared at f26–27, and the shaft is unresolved in the fastest frames (76–87 px/frame)
    - **PARTIAL**
    - 32.6 s; VRAM 11.5 GB; minimum free RAM 2.06 GB; commit 74.4 %; pagefile +39 MB; gen4 x16
  - **`ltx25-m2b-strike-retry`** (the one evidence-driven retry; one change: strike ×1.5 slower, peak 80 → 64 px/frame):
    - metric PASS: +1/0 frames
    - the smear followed the new fast frames (f26–29); the worst frame is less severe (23 % vs 0.9 %)
    - **PARTIAL**; no further retries
    - 31.7 s, same envelope
  - **Proposed:** fast weapon frames are the limit at this envelope. Routes are in open question 9. Not run: M2-C, 768×448.
  - **Storage:** G: 239.14 → 239.08 GiB, with no downloads. Dev scratch was deleted. ₹0 spent.

- **2026-10-02 (late night) · Windows desktop (M2-A: representative temple shot → PASS)**
  - **Scope:** M2-A tests **whole-body rigid translation of a humanoid-shaped proxy** in a representative environment. It is not articulated motion (that is M2-B). Difficulty changed along one axis (synthetic → representative); everything else is R2D's: 512×320×49, static camera, graph, strengths, seed 1000, neutral prompt, corrected control.
  - **Scene:** `build_temple_shot_scene.py`, a procedural courtyard:
    - tiled floor, 8 pillars, a stepped shrine on a platform with steps, walls, rubble, warm low sun
    - a crimson horned proxy (about 2.9 m, upright gold mace) translating left → right while approaching, 6.3 → 5.3 m
    - a static ash-blue proxy with a trident on the shrine (report-only)
  - **Pre-LTX gate passed:**
    - coverage 2.6–3.1 cells wide, 3.8–4.5 tall, 4.9–6.8 cells area
    - travel 4.5 cells; control contrast ≥ 0.41
    - the primary is never occluded; the secondary is occluded in frames 13–47 (intended layering test)
    - the colour tracker reproduces the reference
  - **New reusable pieces:**
    - `control_diagnostic.py` is now spec-driven: coverage, contrast, occlusion, report-only drift; R2D results reproduce unchanged with no spec
    - `experiment_keys.py`: run cache keys via `cachekeys`
    - `tools/windows/run_admission.ps1`
    - 124 tests pass
  - **`ltx25-m2a-temple` (one generation): PASS.**
    - Lateral travel 98.5 %, monotone over 49/49 frames.
    - Within **0–2.8 px of the reference-tracked path**; 7–11 px from GT, which is the tracker's own offset.
    - Area ×1.351 vs GT ×1.385.
    - Structures and layering preserved; structure drift is small (report-only).
    - 32.3 s; VRAM 11.9 GB; minimum free RAM 2.07 GB; commit 74.6 %; pagefile +19 MB; PCIe Gen4 x16.
    - No retry (rule).
  - **Caveat:** the small, long-occluded secondary figure re-emerges degraded (ghosted, smeared).
  - **Observation:** the first frame, not the prompt, sets the character look (the proxies stay primitive).
  - **Documented, not run:** M2-B, M2-C and a same-shot 768×448 comparison.
  - **Storage:** G: 239.16 → 239.14 GiB, with no downloads. ₹0 spent.

- **2026-10-02 (night) · Windows desktop (M3: R2D control diagnostic → PASS)**
  - **New owner constraint:** **no hardware purchases.** The 4070 12 GB, 32 GB RAM and current storage are permanent, and storage efficiency is architectural. Cloud only for a future, narrowly justified training experiment.
  - **Depth input verified against the pinned official path:**
    - `iclora.py`: the guide is bilinear-resized to output/2, RGB, VAE-encoded, then ×2 dilated. There is no depth preprocessing.
    - VDA `gray`: per-clip min–max disparity, near = white, float.
    - **Fixed `make_controls.py`:** p1–p99 clipping → min–max; lossy yuv420p CRF 10 (measured up to 3.7/255 error through ComfyUI's decoder) → lossless full-range H.264 (0 error).
    - The R2 contribution of the two deviations is **unknown**. The path is now aligned with the official preprocessing except for an 8-bit video-input residual.
  - **R2 evidence:** its objects spanned only 0.6–1.5 guide cells (64 px), and its prompt described the motion.
  - **New tools:** `build_control_diagnostic_scene.py` (static camera, red box left → right, blue ball approaching) and `control_diagnostic.py` (ground truth from the object-index pass, a colour-blob tracker validated on the Blender reference, pre-registered rules, contact sheets). 120 tests pass.
  - **Pre-run gate:** the control carries the motion. The box travels 5.15 cells; the ball's area grows ×6.42 with monotone brightening.
  - **`ltx25-r2d-control-diagnostic`** (one generation, neutral motion-free prompt, R2 graph otherwise unchanged): **PASS**.
    - Box centroid within **0.2–2.9 px** of ground truth at 0/25/50/75/100 %, **99.9 %** of travel, monotone over 49/49 frames.
    - Ball area ×6.20 vs ×6.42, non-decreasing.
    - Visual agrees, including a cast shadow that isn't in the control.
    - 33.1 s; VRAM 11.9 GB; minimum free RAM 2.1 GB; commit 74.8 %; pagefile +8 MB; PCIe Gen4 x16.
    - No retry (rule).
  - **Attribution:** R2D changed object scale, the control format and the prompt at once, so the cause of R2's vagueness is not isolated.
  - **Storage:** G: 239.17 → 239.16 GiB, with no downloads. About 4.2 GiB is reclaimable on G: (uv cache), reported only, not deleted.
  - ₹0 spent. M2 not started.

- **2026-10-02 (late) · Windows desktop (M3 started: LTX-2.5 R1 + R2)**
  - **Owner decisions this session:**
    - LTX-2.5 admission goes first, ahead of the FLUX → VACE runbook order.
    - Downloads are staged per rung.
    - After a failure, one evidence-driven mitigation.
    - No quality or upscale additions during admission.
    - Session B, M2, training and cloud stay out of scope.
  - **Tooling:**
    - `monitor.py` records PCIe gen/width (start, under load, end), commit charge/limit and process-tree private bytes.
    - New: `comfy_run.py` (ComfyUI child process, websocket per-phase timings, cold + warm jobs via seed offsets), `make_controls.py` (Blender depth → control mp4), `oc_env.ps1` (session-only caches on G:).
    - 117 tests pass.
  - **Windows Update:**
    - 26200.9457 is installed.
    - Hiding the queued **NVIDIA 591.86 update did not stop it** installing. The owner accepted 591.86 as the new pin.
    - The Intel RST update stayed hidden.
    - Updates are paused until 2026-10-09.
  - **Smart App Control:** it blocked PyAV's unsigned DLL after the reboot. **The owner turned SAC off.**
  - **Runtime:** ComfyUI v0.38.0 + LTXVideo `3bf3ca62` pinned on a dedicated CPython 3.13.16 with torch cu130.
  - **Downloads (SHA-256 == HF LFS):** R1 needed 38.35 GB (INT8 ConvRot transformer and Gemma encoder, video VAE). R2 added only the 0.65 GB Union IC-LoRA (rank 64, 480 modules).
  - **R1a** (T2V 512×320×49, defaults, cold restart): **31.1 s cold / 7.8 s warm**. Peak VRAM 11.9 GB (DynamicVRAM), min free RAM 2.06 GB, commit 74 %, pagefile 69 MB. Owner verdict **pass**: coherent and on-prompt, good backgrounds, faces unclear at this envelope.
  - **R1b** (per-exe Prefer No Sysmem Fallback): byte-identical outputs and no OOM, so fallback was not relied on. The owner restored the setting to *Use global setting (Driver default)*.
  - **R2** (first frame + Blender-depth Union control, stage 1): **32.7 s cold / 8.9 s warm**. The depth control was followed frame by frame (preliminary check). Owner verdict **partial**: motion is present but vague and its direction hard to read in playback; the keyframes track the depth control in a frame-sheet check.
  - **Bottleneck:** system RAM. The first denoise step costs about 12 s (staging 20.5 GB) with a cold or warm file cache.
  - **PCIe:** Gen4 x16, with a brief gen2 x16 window during weight streaming. x4 did not recur.
  - ₹0 spent.

- **2026-10-02 · Windows desktop (M1 → G0 passed)**
  - **Setup.** Cloned to `C:\Users\ADMIN\documents\developer\llm\onecreations-studio` (not OneDrive-synced) and set the repo-local git identity Harshavardhan M.
  - **Installs.**
    - Blender 4.5.14 LTS from the official MSI, with the SHA-256 matched and the Authenticode signature valid. Blender 4.4 was kept.
    - uv 0.12.22, FFmpeg 9.0.2 and 7-Zip 26.03 through winget.
    - The NVIDIA driver 591.74 and system Python 3.12.6 are untouched.
  - **Data root.** `G:\onecreations\` was created. There is no D: drive, and G: has 280 GB free.
  - **Tests.**
    - `uv sync` then `pytest`: **107 passed**, including 11 headless-Blender tests. No code changes were needed.
    - `validate-shot` reports the 2 expected warnings.
    - The Windows Blender numbers match the Mac: projection 0.00053 px; depth planar at 1.54 µm against 0.286 m Euclidean; floor/wall planes within 4.6/5.3 µm; cube mask 0.459 px; identical repeat-export manifests.
  - **iGPU display.** At the owner's direction, the BIOS was set to iGPU Multi-Monitor + IGFX and the monitor moved to the motherboard DP; it still runs 1440p @ 165 Hz.
    Idle 4070 VRAM went from **1167 to 129 MiB** (median of 30 s samples) and idle power from about 10 W to 3 W.
  - **PCIe under load** (Cycles OptiX, about 70 s at 93 % utilisation):
    - Before the reboot: **Gen4 x4** across all 285 busy samples. The GPU is in the CPU x16 slot, and the NVMe has its own CPU M.2 lanes.
    - After the reboot: **Gen4 x16** across all 273 busy samples.
    - No settings were changed, so the cause of the x4 is unknown; monitor it.
  - **Memory.** Commit peak since boot was 16.9 GB against a 58.75 GB limit, with the system-managed pagefile at 27 GB and at most 149 MB used.
  - **check_env.** Exit 0 with 0 FAIL and 3 accepted WARN:
    - the pagefile is system-managed
    - G: has under 500 GB free
    - Blender is not on PATH
  - **Not done, by owner decision:** pagefile, Defender and sysmem-fallback tuning, BIOS PCIe changes, ComfyUI and model weights.
  - **Spend:** ₹0. Session B is not started.
- **2026-10-02 · Mac (Session A)** — Built the hardware-independent core: contracts + JSON Schemas, exact time base/TimeWarp, camera geometry, trajectory library (stats, normalization, retarget + clearance, CSV, minimal COLMAP), shot validator with event schedule, cache-key graph, Blender exporter/importer/trajectory visualizer + diagnostic scene, CLI. Installed Blender 4.5.14 LTS on the Mac (checksum verified; 4.3 kept). 107 tests pass (96 pure, 11 headless Blender). Mac/Blender measurements: Cycles depth is planar (1.4 µm median error vs 0.29 m Euclidean); projection matches `world_to_camera_view` to ≈ 0.0005 px; depth unprojection recovers floor/wall planes to ≈ 6 µm; repeated exports have identical canonical manifests. No GPU work, no spend. Session B not started.
- **2026-10-02 · Mac** — Repo created. Archived v1 research doc. ADR-0001 adopted: 4070-first → H100 only after admission; ₹15,000 hard ceiling (Gate A ₹5,000); LTX-2.5 stays primary candidate; VACE-1.3B is a local experiment; 32 GB RAM stays; LTX inference on 32 GB to be measured, not assumed. Built tooling (env check, monitor, safetensors inspector, hasher, budget ledger) and unit tests (Mac). Nothing installed or measured on the desktop yet. ₹0 spent.
