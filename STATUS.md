# OneCreations Studio — status and handoff

> **Read this first on the Windows desktop.** It is the single source of truth for where the project is,
> what comes next, and the rules that cannot be broken. Update it at the end of every work session
> (see "How to update this file").

| | |
|---|---|
| **Last updated** | 2026-10-02 — Mac session (scaffolding) |
| **Current phase** | **M0 complete → M1 next (desktop setup)**. Handoff from Mac to Windows desktop. |
| **Who acts next** | The Windows desktop (RTX 4070 12 GB · i7-14700K · 32 GB RAM · Windows 11) |
| **External spend** | **₹0 of ₹15,000** · active gate: **Gate A (≤ ₹5,000)** · Gate B: locked |
| **Measured results** | **None yet.** Every number in the docs is published, arithmetic, or proposed — not measured on this machine. |
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
| M1 | Desktop setup: clone, `uv sync`, iGPU display, sysmem-fallback off, pagefile, Blender 4.5 LTS, pinned ComfyUI | Desktop | **G0:** `tools/windows/check_env.ps1` clean, idle VRAM ≈ 0 | ⬜ Next |
| M2 | Diagnostic scene + control export (depth/pose/mask/camera, time map) with convention tests | Desktop | **G1:** all channel-convention checks pass | ⬜ |
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

**Not started (by design, desktop work):** Blender integration/exporters, contracts/schemas package, ComfyUI workflow templates, evaluation metrics, studio UI, job queue. v1 §28 lists the target layout; create folders as work starts — not before.

---

## Open questions for the owner

1. If LTX-2.5 admission is **outcome C**: approve a ≤ 2 h H100 cloud T0 comparison (≤ ₹710)? Or promote the best admitted challenger? (Decide when M3 finishes.)
2. Gate B unlock after the pilot (M8).
3. Where the desktop keeps big data: assumed `D:\onecreations\` (models/, datasets/, caches/, renders/). Change in `docs/runbooks/windows-desktop-setup.md` if different.

---

## How to update this file

At the end of every session on any machine:

1. Update the header table (date, phase, who acts next, spend, measured results).
2. Tick milestones; paste the outcome and the path of the evidence (admission record, eval report).
3. Add a line to the **Session log** (newest first). Keep it factual: what was done, what was measured, what failed.
4. Commit with a plain message, e.g. `status: M3 LTX-2.5 ladder rungs 1-3 measured`, and push.

## Session log

- **2026-10-02 · Mac** — Repo created. Archived v1 research doc. ADR-0001 adopted: 4070-first → H100 only after admission; ₹15,000 hard ceiling (Gate A ₹5,000); LTX-2.5 stays primary candidate; VACE-1.3B is a local experiment; 32 GB RAM stays; LTX inference on 32 GB to be measured, not assumed. Built tooling (env check, monitor, safetensors inspector, hasher, budget ledger) and unit tests (Mac). Nothing installed or measured on the desktop yet. ₹0 spent.
