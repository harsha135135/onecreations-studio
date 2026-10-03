# OneCreations Studio — status and handoff

> **Read this first on the Windows desktop.** It is the single source of truth for where the project is,
> what comes next, and the rules that cannot be broken. Update it at the end of every work session
> (see "How to update this file").

| | |
|---|---|
| **Last updated** | 2026-10-03: Windows desktop, **M2-B** articulated mace strike (run + one retry) |
| **Current phase** | **M0, M0.5 and M1 complete** (G0 passed). **M3 in progress:** LTX-2.5 R1, R2 and **R2D** measured at 512×320×49. R1 pass; R2 partial on motion clarity; **R2D control diagnostic PASS**: an unambiguous Blender-authored motion is followed to within 3 px. **M2 in progress:** **M2-A PASS**: whole-body rigid translation of a humanoid-shaped proxy is followed in a representative temple scene. **M2-B PARTIAL** (2 runs): an articulated strike's timing is followed to the frame and the arm follows every phase, but the fast-moving weapon smears. M2-C and 768×448 are documented, not run. Rungs 3–6, FLUX.2-klein and Wan2.1-VACE are not run. Session B is **not** started. |
| **Who acts next** | **Owner:** choose the next isolated experiment: **M2-C** (authored camera, rigid motion), the **same-shot 768×448** comparison (now proposed on M2-B's strike), or a **weapon-speed sweep** at 512×320. Optionally give a playback verdict on the two M2-B clips. See open questions 6, 8 and 9. **Then the desktop** runs only the chosen one. FLUX.2-klein, Wan2.1-VACE and LTX rungs 4–6 come later. **No hardware purchases**: the 4070 12 GB, 32 GB RAM and current storage are permanent design constraints. |
| **External spend** | **₹0 of ₹15,000** · active gate: **Gate A (≤ ₹5,000)** · Gate B: locked |
| **Measured results** | **LTX-2.5 22B distilled (INT8 ConvRot) on the RTX 4070 + 32 GB RAM, 512×320×49, 8 steps:** <ul><li>T2V: **cold 31.1 s / warm 7.8 s**.</li><li>First frame + Blender-depth Union control: **cold 32.7 s / warm 8.9 s**.</li><li>Owner review: **R1 pass**; **R2 partial** (motion vague in playback).</li><li>**R2D control diagnostic PASS** (static camera, red box left → right, blue ball approaching, neutral prompt):<ul><li>box centroid within 0.2–2.9 px of Blender ground truth, 99.9 % of travel</li><li>ball area ×6.20 vs ×6.42</li><li>generation 33.1 s</li></ul></li><li>**M2-A representative temple shot PASS** (procedural courtyard, rigid humanoid-shaped proxy moving left → right while approaching, static camera, neutral prompt):<ul><li>98.5 % of travel</li><li>within 0–2.8 px of the reference-tracked path</li><li>area ×1.35 vs ×1.39</li><li>structures stable</li><li>32.3 s</li><li>**caveat:** a small (0.44-cell) secondary figure occluded for about 35 frames re-emerges degraded</li><li>the first frame, not the prompt, sets the character look</li></ul></li><li>**M2-B articulated mace strike PARTIAL** (same temple, static camera, rigged proxy with a fixed root, M2-A prompt unchanged):<ul><li>weapon apex / contact on the authored frames: 0 / 0 frames off (retry +1 / 0)</li><li>excursion 102 % of GT</li><li>body within 2.6 px of GT (no invented translation)</li><li>the arm visibly changes pose through guard → wind-up/apex → strike/contact → recovery</li><li>**but** in the fastest strike frames (76–87 px/frame) the weapon is ghosted/smeared and the shaft vanishes</li><li>the one retry (strike ×1.5 slower, peak 64 px/frame) reduced but did not remove it; the smear follows the fast frames</li><li>`joints.npz` verified in a real scene: projected weapon bone within 0.57 px of the render</li><li>31.7–32.6 s, same memory envelope</li></ul></li><li>The depth control is now aligned with the official preprocessing (per-clip min–max disparity, lossless), except for an 8-bit video-input residual.</li><li>The binding resource is **system RAM**: minimum free about 2.0 GB, commit ≤ 75 %, no paging (pagefile ≤ 156 MB).</li><li>VRAM peaks at about 11.9 GB by DynamicVRAM design, with **no sysmem fallback**: R1b, run without it, is byte-identical.</li><li>The PCIe link is Gen4 x16, with a brief gen2 x16 window during weight streaming.</li></ul>Details: `docs/measurements/2026-10-02-ltx25-r1-r2.md`, `2026-10-02-ltx25-r2d-control-diagnostic.md`, `2026-10-02-m2a-temple-shot.md` and `2026-10-03-m2b-temple-strike.md`. Desktop baseline: `2026-10-02-desktop-m1.md` and `2026-10-02-post-update-r1-setup.md`. Mac contract numbers: `docs/contracts.md`. |
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
| M2 | Use the Session A exporter on the first real scene (V0 rigs + environment); extend the diagnostic checks only where the real scene needs it (pose visibility, Cryptomatte if compositing requires it) | Desktop | **G1:** Windows Blender tests pass + a real-scene export bundle validates | 🟡 **In progress.** **M2-A ✅ PASS** (2026-10-02): a representative temple scene exported and validated through the Session A exporter, with rigid-translation control followed (`docs/measurements/2026-10-02-m2a-temple-shot.md`). **M2-B 🟡 PARTIAL** (2026-10-03): first rigged actor and first real use of the armature/joint export and `ActionTimeline`; strike timing followed to the frame, but the fast weapon smears (`docs/measurements/2026-10-03-m2b-temple-strike.md`). Next, isolated: **M2-C** (camera move, rigid subject); not started |
| M3 | Admission ladders: LTX-2.5 (INT8 ConvRot + offload), FLUX.2-klein-4B, Wan2.1-VACE-1.3B | Desktop | **G2:** outcome A/B/C recorded for each in `admission_records/` + `model_registry/models.yaml` | 🟡 **In progress.** LTX-2.5 **R1 (T2V) and R2 (first frame + depth Union) run reliably** at 512×320×49 (owner: R1 pass, R2 partial). The **R2D control diagnostic passed**: the Union depth control is clearly followed (2026-10-02; `docs/measurements/2026-10-02-ltx25-r1-r2.md`, `…-r2d-control-diagnostic.md`). Not yet run: LTX rungs 3–6, FLUX.2-klein, Wan2.1-VACE. No A/B/C outcome yet |
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
| `workflows/ltx25/` | API-format R1 (T2V video-only) and R2 (first frame + depth Union) workflows, plus R2D, M2-A and M2-B variants, with deviations from the official graphs documented | Used for R1–M2-B |
| `admission_records/` | `records.jsonl` (+ per-run CSV, comfy reports, specs, inspect/compare JSON, cache keys) for ltx25-r1a, r1b, r2, r2d, m2a-temple, m2b-strike, m2b-strike-retry | Measured |
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
| `src/onecreations/contracts/` + `schemas/` | Pydantic contracts: Project, CharacterAsset, CameraMotion, ActionTimeline, TimeWarp, VFXEvent, Shot, ModelBackend, ExperimentRecord, AdmissionRecord, ExportManifest; generated JSON Schemas | Tested on Mac |
| `src/onecreations/timebase.py` | Exact rational time, frame rates (incl. 24000/1001), TimeWarp with holds | Tested; shared with Blender scripts |
| `src/onecreations/geometry/` | Quaternions, Blender↔OpenCV conventions, rigid validation, Blender intrinsics → K, projection | Tested; verified against Blender 4.5 |
| `src/onecreations/camera/` | Trajectories (spline/slerp), stats, normalize (up/scale/provenance), retarget + clearance report, CSV, minimal COLMAP import | Tested on Mac |
| `src/onecreations/shotpkg/` | Project loader + shot cross-reference validator + event schedule | Tested on Mac |
| `src/onecreations/cachekeys.py`, `hashing.py` | Canonical JSON, content/array digests, artifact dependency graph | Tested on Mac |
| `src/onecreations/blender_bridge.py`, `blender_bundle.py` | Find/run Blender headless; load + verify export bundles | Tested on Mac and Windows (Blender 4.5.14) |
| `integrations/blender/` | `build_diagnostic_scene.py`, `oc_export.py`, `oc_import_camera.py`, `oc_visualize_trajectory.py` | Tested on Mac and Windows; numbers agree (see `docs/contracts.md`) |
| `examples/diagnostic/` | Fixture project from v1's own numbers (contact 0.90 s, 6 s shot, impact hold); backend profile is a labelled test fixture | Validates (2 expected warnings) on both machines |

All tests pass on the Windows desktop: 107 at M1, 117 with the admission tooling, 120 with the R2D control-diagnostic tooling, 124 at M2-A, **132** at M2-B (Python 3.12.6 via uv 0.12.22).

**Not started:** Session B (VFX event system, dataset/provenance pipeline, 12-shot evaluation framework), ComfyUI workflow templates, studio UI, job queue. Deferred Session A items are listed in `docs/contracts.md` (Cryptomatte decoding, beauty renders, motion vectors, joint visibility, sub-frame pass rendering, auto path adjustment, COLMAP distortion/gyro, visualizer preview renders).

### Next on the desktop (owner decides the order)

1. **M2-A done (PASS); M2-B done (PARTIAL).** Choose next, one axis at a time. Designs: `docs/measurements/2026-10-02-m2a-temple-shot.md` §7–8 and `2026-10-03-m2b-temple-strike.md` §7.
   - **M2-C:** the same temple and rigid proxy translation, plus one authored camera move (`CameraMotion`). Measure structure parallax and subject screen trajectory.
   - **Same-shot 768×448:** now proposed on **M2-B's strike**, with only the resolution changed. Does more resolution sharpen the fast weapon? Also measure control fidelity, VRAM, RAM and runtime. RAM is the binding resource (about 2.05 GB free at 512×320).
   - **Weapon-speed sweep** (512×320): the same strike at about 1.0 / 0.7 / 0.5 cells per frame, to locate the smear threshold.
   - The guaranteed route for fast weapon frames is to composite them from the Blender beauty pass (hard rule 8). It is proposed, not built.
   - No 960×544 or upscaler first.
   - **Working heuristics (proposed, not proven rules):**
     - control-relevant subjects should span ≥ about 2 Union-guide cells (64 px each at 512×320)
     - avoid long occlusions of small secondary subjects, or composite them from the Blender beauty pass
     - the first frame sets the look
     - fast weapon frames: a ~1-cell weapon moving faster than ~0.7 cell/frame smears at 512×320×49 (M2-B); contact and hold frames render solidly
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
6. **Quality ladder:** approve the **same-shot 768×448** comparison, with only the resolution changed? It is justified by M2-A's pass, and M2-B now gives it a sharper question: on M2-B's strike, does more resolution fix the fast-weapon smear? 960×544 and the official upscaler (1 GB) stay deferred; RAM headroom is the limit.
7. **Smart App Control** is off (owner, 2026-10-02), because it blocked PyAV's unsigned DLL. Keep it off on this ML workstation?
8. **Next M2 experiment:** M2-C (authored camera, rigid motion) is the remaining isolated M2 axis; M2-B is done (PARTIAL). It does not start automatically.
9. **M2-B fast-weapon smear:** which route first? (a) the 768×448 same-shot comparison on the strike, (b) a weapon-speed sweep at 512×320, or (c) only plan to composite fast weapon frames from the Blender beauty pass (hard rule 8) and move on. Optional: a playback verdict on the two M2-B clips, recorded separately from the classification.

---

## How to update this file

At the end of every session on any machine:

1. Update the header table (date, phase, who acts next, spend, measured results).
2. Tick milestones; paste the outcome and the path of the evidence (admission record, eval report).
3. Add a line to the **Session log** (newest first). Keep it factual: what was done, what was measured, what failed.
4. Commit with a plain message, e.g. `status: M3 LTX-2.5 ladder rungs 1-3 measured`, and push.

## Session log

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
