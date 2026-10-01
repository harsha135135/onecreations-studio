# OneCreations Studio — status and handoff

> **Read this first on the Windows desktop.** It is the single source of truth for where the project is,
> what comes next, and the rules that cannot be broken. Update it at the end of every work session
> (see "How to update this file").

| | |
|---|---|
| **Last updated** | 2026-10-02 — Mac session A (hardware-independent core) |
| **Current phase** | **M0 + M0.5 (Mac core, Session A) complete → M1 next (desktop setup)**. Session B is **not** started (owner decides when). |
| **Who acts next** | The Windows desktop (RTX 4070 12 GB · i7-14700K · 32 GB RAM · Windows 11) |
| **External spend** | **₹0 of ₹15,000** · active gate: **Gate A (≤ ₹5,000)** · Gate B: locked |
| **Measured results** | **No GPU/model measurements yet.** Mac-only data-contract checks on Blender 4.5.14 (CPU): Cycles depth is planar, projection matches Blender to ≈ 0.0005 px — see `docs/contracts.md`. Not 4070 results. |
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
| M1 | Desktop setup: clone, `uv sync`, iGPU display, sysmem-fallback off, pagefile, Blender 4.5 LTS, pinned ComfyUI | Desktop | **G0:** `tools/windows/check_env.ps1` clean, idle VRAM ≈ 0, `uv run pytest -q` passes (incl. `-m blender` on Windows Blender 4.5) | ⬜ Next |
| M2 | Use the Session A exporter on the first real scene (V0 rigs + environment); extend the diagnostic checks only where the real scene needs it (pose visibility, Cryptomatte if compositing requires it) | Desktop | **G1:** Windows Blender tests pass + a real-scene export bundle validates | ⬜ |
| M3 | Admission ladders: LTX-2.5 (INT8 ConvRot + offload), FLUX.2-klein-4B, Wan2.1-VACE-1.3B | Desktop | **G2:** outcome A/B/C recorded for each in `admission_records/` + `model_registry/models.yaml` | ⬜ |
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
| `docs/runbooks/windows-desktop-setup.md` | M1 step-by-step | Ready to execute |
| `docs/runbooks/admission-ladder.md` | M3 procedure + record format | Ready to execute |
| `docs/runbooks/local-training.md` | M6 procedure (T1, VACE-1.3B, LTX prep) | Ready; trainer commits to pin |
| `docs/runbooks/cloud-h100.md` | M7 procedure, cost controls | Ready; locked behind G4 |
| `tools/windows/check_env.ps1` | Read-only environment check (G0) | Written on Mac — **not yet run on Windows** |
| `tools/admission/monitor.py` | Runs a command, samples GPU/RAM/pagefile, writes CSV + JSONL summary | Tested on Mac (no-GPU path only) |
| `tools/inspect_safetensors.py` | Header-only tensor/LoRA-rank inspector (no weight load) | Tested on Mac with synthetic file |
| `tools/registry/hash_files.py` | Streaming SHA-256 for model files → registry | Tested on Mac |
| `tools/budget/ledger.py` + `budget/` | Spend ledger with gate enforcement | Tested on Mac |
| `model_registry/models.yaml` | Candidate models, roles, licenses, admission status, `hash: TODO` | Hashes/commits TODO on desktop |
| `training/**/experiment-card*.yaml` | Experiment cards for T1, VACE-1.3B, LTX T2 (not trainer-native configs) | Proposed; trainer configs to be derived from pinned upstream examples |
| `docs/contracts.md` | Conventions, contracts, issue codes, cache-key graph, export bundle format, Mac measurements, deferred list | Reference |
| `src/onecreations/contracts/` + `schemas/` | Pydantic contracts: Project, CharacterAsset, CameraMotion, ActionTimeline, TimeWarp, VFXEvent, Shot, ModelBackend, ExperimentRecord, AdmissionRecord, ExportManifest; generated JSON Schemas | Tested on Mac |
| `src/onecreations/timebase.py` | Exact rational time, frame rates (incl. 24000/1001), TimeWarp with holds | Tested; shared with Blender scripts |
| `src/onecreations/geometry/` | Quaternions, Blender↔OpenCV conventions, rigid validation, Blender intrinsics → K, projection | Tested; verified against Blender 4.5 |
| `src/onecreations/camera/` | Trajectories (spline/slerp), stats, normalize (up/scale/provenance), retarget + clearance report, CSV, minimal COLMAP import | Tested on Mac |
| `src/onecreations/shotpkg/` | Project loader + shot cross-reference validator + event schedule | Tested on Mac |
| `src/onecreations/cachekeys.py`, `hashing.py` | Canonical JSON, content/array digests, artifact dependency graph | Tested on Mac |
| `src/onecreations/blender_bridge.py`, `blender_bundle.py` | Find/run Blender headless; load + verify export bundles | Tested on Mac (Blender 4.5.14) |
| `integrations/blender/` | `build_diagnostic_scene.py`, `oc_export.py`, `oc_import_camera.py`, `oc_visualize_trajectory.py` | Tested on Mac — **re-run on Windows in M1** |
| `examples/diagnostic/` | Fixture project from v1's own numbers (contact 0.90 s, 6 s shot, impact hold); backend profile is a labelled test fixture | Validates (2 expected warnings) |

**Not started:** Session B (VFX event system, dataset/provenance pipeline, 12-shot evaluation framework), ComfyUI workflow templates, studio UI, job queue. Deferred Session A items are listed in `docs/contracts.md` (Cryptomatte decoding, beauty renders, motion vectors, joint visibility, sub-frame pass rendering, auto path adjustment, COLMAP distortion/gyro, visualizer preview renders).

### M1 checklist for the desktop (in order)

1. Follow `docs/runbooks/windows-desktop-setup.md` (iGPU display, sysmem fallback off, pagefile, Blender 4.5 LTS, uv).
2. `uv sync` then `uv run pytest -q`. The 11 Blender tests run if Blender 4.5 is found (default install path or `$env:ONECREATIONS_BLENDER`); they must pass on Windows too — record any numeric differences from `docs/contracts.md`.
3. `uv run onecreations blender info` (should report the pinned 4.5 series) and `uv run onecreations validate-shot examples/diagnostic`.
4. `powershell -ExecutionPolicy Bypass -File tools\windows\check_env.ps1` → G0.
5. Update this file and push; then M2/M3.

---

## Open questions for the owner

1. If LTX-2.5 admission is **outcome C**: approve a ≤ 2 h H100 cloud T0 comparison (≤ ₹710)? Or promote the best admitted challenger? (Decide when M3 finishes.)
2. Gate B unlock after the pilot (M8).
3. Where the desktop keeps big data: assumed `D:\onecreations\` (models/, datasets/, caches/, renders/). Change in `docs/runbooks/windows-desktop-setup.md` if different.
4. When to run Session B (VFX events, dataset/provenance, evaluation framework): on the Mac before M1, or after the first GPU measurements. Not started automatically.

---

## How to update this file

At the end of every session on any machine:

1. Update the header table (date, phase, who acts next, spend, measured results).
2. Tick milestones; paste the outcome and the path of the evidence (admission record, eval report).
3. Add a line to the **Session log** (newest first). Keep it factual: what was done, what was measured, what failed.
4. Commit with a plain message, e.g. `status: M3 LTX-2.5 ladder rungs 1-3 measured`, and push.

## Session log

- **2026-10-02 · Mac (Session A)** — Built the hardware-independent core: contracts + JSON Schemas, exact time base/TimeWarp, camera geometry, trajectory library (stats, normalization, retarget + clearance, CSV, minimal COLMAP), shot validator with event schedule, cache-key graph, Blender exporter/importer/trajectory visualizer + diagnostic scene, CLI. Installed Blender 4.5.14 LTS on the Mac (checksum verified; 4.3 kept). 107 tests pass (96 pure, 11 headless Blender). Mac/Blender measurements: Cycles depth is planar (1.4 µm median error vs 0.29 m Euclidean); projection matches `world_to_camera_view` to ≈ 0.0005 px; depth unprojection recovers floor/wall planes to ≈ 6 µm; repeated exports have identical canonical manifests. No GPU work, no spend. Session B not started.
- **2026-10-02 · Mac** — Repo created. Archived v1 research doc. ADR-0001 adopted: 4070-first → H100 only after admission; ₹15,000 hard ceiling (Gate A ₹5,000); LTX-2.5 stays primary candidate; VACE-1.3B is a local experiment; 32 GB RAM stays; LTX inference on 32 GB to be measured, not assumed. Built tooling (env check, monitor, safetensors inspector, hasher, budget ledger) and unit tests (Mac). Nothing installed or measured on the desktop yet. ₹0 spent.
