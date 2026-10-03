# M2-B — articulated mace strike in the temple, static camera — 2026-10-03

**Question:** does the Blender → depth control → LTX-2.5 path follow **articulated** motion — a limb and a weapon moving
with the right timing — rather than only whole-body rigid motion (M2-A)?

**Answer for this test: M2-B = PARTIAL** (one generation + the one permitted evidence-driven retry; both PARTIAL).

- **Followed, measured:** the timing is followed: the weapon's apex and contact land on the authored frames (0/0 frames off; retry +1/0). Its excursion is 102 % of GT. The body stays put (within 2.6 px), and the weapon arm visibly changes pose through every phase.
- **Not clean:** in the **fastest strike frames** the weapon is **materially smeared/ghosted**, and the shaft linking hand and mace is not resolved. Under the pre-registered rule (owner, 2026-10-03), that is PARTIAL.
- Slowing the strike ×1.5 made the worst frame much less severe but did not remove the smear: it followed the new fast frames.

All figures are **measured**, single observation per run, unless labelled otherwise.

**Constraints:**
- no hardware purchases; RTX 4070 12 GB + 32 GB RAM + existing storage
- no cloud, training, new downloads, Wan, FLUX, upscaler, 960×544 or 768×448
- no system changes
- one generation plus at most one evidence-driven retry (used once, after run 1's PARTIAL)

## 1. What changed vs M2-A (one axis: rigid → articulated)

**Same as M2-A:**
- the procedural temple and camera (static, (0, −10, 2.2), 6° down, 35 mm), 512×320 × 49 frames at 24 fps
- the graph `workflows/ltx25/m2b_strike_api.json`, node-for-node M2-A (only the output prefix changed): INT8 ConvRot transformer + Gemma, Union IC-LoRA 1.0, guide strength 1, first-frame strength 1, stage 1, 8 distilled steps, `euler_ancestral`, CFG 1, seed 1000
- **the M2-A prompt, verbatim** (neutral; no motion words)
- the corrected depth control (per-clip min–max disparity, lossless full-range)
- driver-default sysmem

**New:** a rigged humanoid proxy performing **one articulated action**, with its **root and legs never keyed**: no translation, so any movement is articulation.

The environment is built by the same code as M2-A: `build_temple_shot_scene.py` was refactored into reusable builders with no behaviour change, verified in §8. The only environment difference is the shrine finial, which is stone here, so gold is unique to the weapon.

## 2. Scene (`integrations/blender/build_temple_strike_scene.py`; assets on G: at `G:\onecreations\renders\m2b_strike\`)

**Actor `m2b_asura`** (pass 1): the M2-A crimson proxy, as **one rigidly skinned mesh**. Each primitive is weighted 1.0 to one bone of `m2b_asura_rig`, which has 16 bones: root, pelvis, spine, chest, head, both arms (upper/forearm/hand), both legs (thigh/shin), and a `mace` bone on the left hand whose tail is the mace-head centre.
- Iron pauldrons and ivory horns, so the **gold mace head is the only gold object in the scene**.
- Feet fixed at (−1.8, −4.0), about 6 m from the camera, left of centre; the static ascetic `m2a_shiva` stays visible.

**Weapon:**
- `m2b_mace_head` (pass 8): a gold sphere, r 0.34 m, 0.9–1.0 guide cells
- `m2b_mace_shaft` (pass 9): iron
- both skinned to `mace`

**Choreography** (an `ActionTimeline`, `m2b_mace_strike_v1`, validated with the contract and stored in the spec and `action_timeline.json`). Poses are grip/mace targets in rig space, solved with an analytic two-bone IK into FK quaternion keys.

| Phase (kind) | Blender frames | What happens |
|---|---|---|
| guard (idle) | 1–8 | mace low and diagonal (head 2.0 m) |
| windup (other) | 8–24 | Bezier; the arm lifts and the mace comes up to near vertical; chest leans back and twists |
| **apex** | 24 | head at its highest point, 2.96 m (17 px below the top edge) |
| strike (strike) | 24–30 | quad ease-in, then constant speed: a forward-downward chop on the weapon side, kept clear of the torso so the depth control carries it against the background |
| **contact** | 30 | head on the floor (centre 0.34 m) |
| impact (impact) | 30–35 | hold |
| recovery (recovery) | 35–49 | the mace swings outward and up to a low guard, never lower on screen than the contact |

**Spec:** `shot_spec.json` (copied to `admission_records/2026-10-03_ltx25-m2b-strike_shot_spec.json`) holds the scene, the choreography and the **pre-registered tracking, gate, checks and classification**, written before the run. The classification includes the owner's articulation criterion (§6).

**References:** `first_frame.png` and `reference_preview.mp4` come from the new `integrations/blender/render_reference.py`:
- Cycles OptiX on the 4070, 64 spp, seed 0, OIDN on the CPU, no motion blur
- the preview is lossless (libx264rgb −qp 0)
- 25.5 s for 49 frames
- a sidecar records the settings and the SHA-256s

It replaces the ad-hoc reference renders used up to M2-A.

## 3. New analysis (`tools/admission/control_diagnostic.py`, back-compatible)

All of these are spec-driven; R2D and M2-A behaviour is unchanged.

**Colour rule `gold`:** b < 0.55 g, which keeps warm sunlit stone (b ≈ 0.75 g) out.

**Check `timing`** (every frame, not only the checkpoints):
- apex = highest on screen (min cy)
- contact = the first frame after the fastest move following the apex from which the head moves ≤ 4 px to the next frame. It uses 2D speed because the last strike frame moves mostly sideways on screen.
- pre-registered: |Δapex|, |Δcontact| ≤ 2 frames; a downswing with excursion ≥ 50 % of GT; detected in ≥ 90 % of frames; the x direction checked only when GT moves ≥ 32 px sideways (here 16.5 px, so not applicable)

**Check `position`** (stationary root):
- displacement from frame 0 within 32 px (0.5 cell) of GT at each checkpoint
- area relative to frame 0 within ±25 %

Both are relative to frame 0, so the constant colour-tracker offset cancels. This catches invented translation and a body that breaks up.

**Gate options:**
- per-subject threshold overrides
- `ignore_occluders` (the body ignores its own mace)
- contrast gated at the GT apex and contact
- visible in every frame
- not cut by the frame border
- minimum excursion

**Joint cross-check** (first real-scene use of `joints.npz`):
- the `mace` bone tail projected with `onecreations.geometry.intrinsics.project` against the head's object-index centroid
- the stationary bones
- **timeline agreement:** the exported motion's apex and contact against the ActionTimeline boundaries, in 3D and on screen

There is also an event contact sheet covering apex − 2 … contact + 2.

## 4. Control validated before LTX (`control_diagnostic.py inspect --spec`): gate PASSED

| | Value |
|---|---|
| Body coverage (checkpoints) | 2.5–3.0 cells wide, 3.7 tall, 5.0–5.4 cells area; never occluded (own mace ignored); in frame |
| Mace-head coverage | 0.91–1.02 cells wide/tall, 0.64–0.80 cells area (gate 0.75 / 0.4); visible and in frame in all 49 frames |
| Mace-head excursion | 222 px = **3.47 cells** (gate 2) |
| Control contrast | body ≥ 0.30; head ≥ 0.16 on **every** frame (0.16 at contact, 0.57 at apex): the arc never crosses the torso |
| Joint projection vs object index | **max 0.57 px, median 0.30 px** (gate 3 px) over 49 frames |
| Stationary bones (root, pelvis, thighs, shins) | **0.0 m** |
| Events vs ActionTimeline (expected apex 23, contact 29, output frames) | 3D joints 23 / 29; screen GT 23 / 29 (**0 / 0 frames**) |
| Colour trackers on the Blender reference | timing 23 / 29 exactly; body displacement ≤ 0.2 px; area ≤ 1 %. Constant offset 7.2–7.4 px (non-red pauldrons and horns in the GT mask) |
| Secondary `m2a_shiva` | partly occluded in 8 frames (mace passes at f25–26, f43–48); report-only |

## 5. Runs

**Inputs:**
- workflow `ef4340c2…` for both runs
- run 1: first frame `4e7dcb1b…`, control `a1348e7c…`, bundle `910716dc…`
- retry: first frame `b2557f97…`, control `eb98638b…`, bundle `62558492…`
- the two first frames are the same guard pose and differ in 22 of 163,840 pixels by one 8-bit level (render noise)
- models (registry): `c4279eef…`, `6ce688a0…`, `847e14ca…`, LoRA `a1b888a8…`
- conditions: Chrome closed; 23.0 / 23.6 GB RAM free at the start; updates paused until 2026-10-09

| | `ltx25-m2b-strike` | `ltx25-m2b-strike-retry` |
|---|---|---|
| Change | — | **strike stretched ×1.5 in time** (6 → 9 frames, contact at Blender frame 33, mid key on 28.5); the impact hold shortens 5 → 2 frames; path, poses, guard, wind-up, apex, recovery, prompt, graph and seed unchanged |
| GT peak head speed | **80.1 px/frame** (1.25 cells/frame) | **64.1 px/frame** (1.0 cells/frame) |
| Cache keys (control_render / generation) | `870cc67d…` / `284cf311…` | `a3614984…` / `7b5e58a0…` |
| Output SHA-256 | `9161ed7d…f02c367f` | `2241f367…86ba00e2` |
| Startup / generation | 29.0 s / **32.6 s**: load 3.7, text encode 8.8, denoise 16.7 (first step 11.9 s, then median 0.594 s/step), decode 1.9 | 7.1 s / **31.7 s**: load 3.4, text encode 7.8, denoise 16.9 (first step 11.9 s, then median 0.594), decode 2.0 |
| Peak VRAM | 11,495 MiB (DynamicVRAM) | 11,501 MiB |
| RAM | peak 30,445 MB; **minimum free 2,064 MB** | peak 30,459 MB; minimum free 2,050 MB |
| Commit | 44,780 of 60,157 MB (74.4 %) | 45,121 MB (75.0 %) |
| Pagefile | peak 69 MB, growth 39 MB | peak 171 MB, growth 103 MB |
| PCIe under load | gen4 x16 ×6 | gen4 x16 ×11 |

Same envelope as R1/R2/R2D/M2-A; no paging pressure.

## 6. Analysis (`control_diagnostic.py compare --spec`) and classification

Contact sheets and full-resolution crops are kept outside Git, in `G:\onecreations\renders\m2b_strike[_retry]\analysis\`:
- `compare_contact_sheet.png`
- `compare_event_contact_sheet.png`
- `actor_phase_crops.png`
- `strike_zoom_*.png`

Numbers: `admission_records/2026-10-03_ltx25-m2b-strike[-retry]_compare.json` and `…_smear_evidence.json`.

### Quantitative (pre-registered): metric class PASS in both runs

| | Run 1 | Retry |
|---|---|---|
| Apex frame, generated / GT | **23 / 23** | 24 / 23 (+1, within ±2) |
| Contact frame, generated / GT | **29 / 29** | **32 / 32** |
| Excursion, generated / GT | 226.2 / 222.3 px (**102 %**) | 227.1 / 222.3 px (102 %) |
| Head detected | 49 / 49 frames | 49 / 49 |
| Body displacement error vs GT (checkpoints) | 0.0–**2.6 px** | 0.0–2.1 px |
| Body relative-area error | ≤ 5.7 % | ≤ 4.7 % |
| Static-structure drift (report-only) | ≤ 0.0063 (reference ≤ 0.0037) | ≤ 0.0051 |

### Visual inspection (documented; the owner's articulation criterion, pre-registered in the spec)

> PASS requires that the weapon arm visibly changes pose through guard → wind-up/apex → strike/contact → recovery. It must not show the mace moving independently, the limb materially smearing or ghosting, or the whole actor translating.

**What holds, in both runs:**
- The arm visibly changes pose through every phase, matching the reference:
  - guard: hand at the hip, mace diagonal
  - wind-up: arm lifting, mace rising
  - apex: mace vertical, hand at the shoulder
  - strike: the elbow bend and forearm direction at f27–29 match the reference
  - contact: mace on the floor, arm extended down
  - recovery: back to a low guard
- The actor does not translate.
- Timing reads exactly as authored. During the hold the head is solid, only slightly soft-edged, and the shaft is visible.

**What fails the criterion:**

- **Run 1:** in the three fastest frames, where the head moves 76–87 px/frame:
  - **f25:** the head is a **semi-transparent ghost**; the gold mask keeps 0.9 % of the reference area
  - **f26–f27:** it is a noisy blob with fuzzy edges
  - **f25–f27:** the **shaft, the visible hand–weapon link, is not resolved**
  - **f23–f26:** the hand and forearm read as a lump
  - from f28 (incoming 48 px/frame) the head is solid again and the shaft returns
- **Retry:** the smear **moves with the fast frames**, now f26–f29 at 43–64 px/frame:
  - the head is again a noisy blob, and the shaft is not resolved
  - the worst frame is much less severe (gold area 23 % of the reference at f26, against 0.9 %), and there is no near-total ghost

**Per-frame evidence** (`…_smear_evidence.json`, report-only): the deepest gold-area dip in each run falls on the frame entering the fastest jump. Run 1: f25, 0.009, with outgoing speed 80. Retry: f26, 0.23, with outgoing speed 43 followed by 64. The edge-energy ratio is too noisy to discriminate (0.75–1.1 even in held frames).

### Classification: **PARTIAL** (run 1), **PARTIAL** (retry)

- The weapon moves the right way with the right timing, and the arm articulation is coherent.
- But the weapon is materially smeared or ghosted, and visibly detached from the hand, during the strike's fastest frames. These are exactly the frames a parry or impact lives in.
- **No further retry** (rule).
- **Owner playback verdict:** not required for classification; not given yet. Record it here separately if given.

## 7. What this means

**Confirmed at this scope:**
- Articulated, limb-level motion authored in Blender is carried by the Union depth control, and LTX-2.5 reproduces its **timing** to the frame: apex and contact.
- A stationary actor stays stationary.
- The joint export (`joints.npz`) agrees with the render to 0.57 px. The ActionTimeline matches the exported motion exactly.

**Limit found:**
- At 512×320 × 49 with 8 distilled steps, a small weapon (about 1 guide cell) moving faster than roughly **0.7 cell/frame (≈ 45 px/frame)** is rendered as a smear, and its thin shaft disappears.
- Stretching the strike ×1.5 reduced but did not remove the effect, and it tracked the fast frames.
- The exact threshold and its dependence on resolution are **not isolated** (proposed, not proven: it may also depend on the object's size and contrast).

**Proposed implications for the V1 parry (not run):**
- **Hard rule 8 route:** composite the weapon (and, if needed, the hand) from the Blender beauty pass in the fast frames. The Blender path always delivers, and the geometry, joints and timing are already exact.
- **Measurement routes, one axis each, owner's call:**
  - the planned **same-shot 768×448** comparison, run on M2-B's strike rather than M2-A: does more resolution sharpen fast thin objects, or does the higher per-frame pixel speed make it worse?
  - a **per-frame-speed sweep** at 512×320, the same strike at 1.0 / 0.7 / 0.5 cells per frame, to locate the threshold
- **Choreography design rule (proposed):** keep fast weapon frames few, and keep the weapon ≥ 1 guide cell and clear of the torso. Let contact and hold frames carry the readability; they render crisply here.

## 8. Shared environment refactor: verified neutral

`build_temple_shot_scene.py` now exposes `setup_scene`, `make_materials`, `add_camera`, `build_environment(finial=…)`, `add_shiva`, `add_sun` and `scene_spec`.

Rebuilding M2-A with it gives:
- a spec identical to `admission_records/2026-10-02_ltx25-m2a-temple_shot_spec.json`
- **bit-identical depth and object-index passes** (so an identical depth control)
- identical camera, object and probe arrays

The bundle `content_sha256` differs **only** through the normal pass: |Δ| ≤ 1.5e-5 (float32 noise).

The same noise appears when rebuilding with the **pre-refactor** script (≤ 1.5e-5 against the original, 8.9e-6 between the two rebuilds). Re-exporting the saved M2-A `.blend` reproduces `5ac57790…` bit for bit.

So **re-exporting a saved `.blend` is bit-reproducible; rebuilding a scene from script is reproducible in depth and index, with normal-pass float noise.** Noted in `docs/contracts.md`.

The default `build_temple_strike_scene.py` (no `--strike-frames`) reproduces run 1's spec and timeline exactly.

## 9. Storage

| | Before | After |
|---|---|---|
| G: free | 239.14 GiB | 239.08 GiB: renders 2 × 28 MB, run outputs 2 × 80 KB, no downloads |

- No model files were added or duplicated: the 4 pinned files, 36.3 GiB.
- Dev scratch (`G:\onecreations\temp\m2a_regress`, `…\m2b_dev`) was deleted after use.
- Media, renders and `.blend` files stay on G:. Git holds only source, docs, tests and small JSON/CSV records.
