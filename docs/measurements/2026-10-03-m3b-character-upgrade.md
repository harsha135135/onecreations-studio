# M3-B — character / first-frame appearance upgrade + hybrid v2 — 2026-10-03

**Status: PREPARED, NOT RUN.** The scene code, compositor rule, gate tooling, tests and pre-registration are done. No M3-B scene was built, nothing was rendered or generated, and nothing was measured. **There is no CONTROL, APPEARANCE or hybrid-v2 result yet.**

**Why it stopped:** this session ran in a cloud Linux container, not on the Windows desktop. The project rules say GPU work runs only on the desktop (`CLAUDE.md`, ADR-0001), and that container could not do it. Observed in the container:
- `nvidia-smi`: command not found (no GPU)
- `blender`: not installed; `download.blender.org` refused by the network policy (proxy 403)
- the data root `G:\onecreations\` (LTX weights, the M3-A export bundle and renders) does not exist there

So every Blender gate, the one generation, the evaluation and the resource telemetry have to run on the desktop. §8 gives the exact sequence. A generation result can't be produced from a machine without the GPU, the weights or the M3-A renders, and none is claimed here.

Labels: **measured** = observed by running code (here, only synthetic unit tests and CPU test suites); **proposed** = a pre-registered threshold or design choice; nothing here is a desktop measurement.

## 1. Question

On the unchanged M3-A shot, the question has two parts:
- Does a finished-character Blender first frame make the characters read as finished characters in the LTX-2.5 output, while control is kept? The first frame has continuous sculpted bodies, layered costume and armour, and readable faces.
- Does the pre-registered hybrid v2 make the protected weapon usable without a double image?

## 2. What changes and what does not

**Changed:** only the two characters' geometry and materials. After generation, the compositor's ghost rule also changes (hybrid v2, §4).

**Unchanged (M3-A):**
- the temple and its finished look (`oc_lookdev`) and the banners
- rig `m3a_asura_rig`, the M2-B keys and root (−1.8, −4.0), the original-speed strike
- ActionTimeline `m3a_mace_slam_v1` (apex 23, contact 29)
- CameraMotion `m3a_orbit_push_in_v1`
- the defender's placement, yaw and static pose (trident on the M3-A diagonal)
- **the M3-A mace** (geometry, materials, passes 8/9)
- the dust effect and its trigger
- object ids and pass indices, every tracking rule and tolerance
- 512×320×49, the LTX graph and the **M3-A prompt verbatim**

`workflows/ltx25/m3b_character_api.json` differs from `m3a_action_api.json` only in the output prefix and two node titles. A test enforces this.

**Implementation:**
- `integrations/blender/build_m3b_scene.py` calls `build_temple_action_scene.build(variant=...)`.
- That `variant` hook is new. Its default (`None`) builds M3-A exactly as before. The M3-A mace builder was split out as `build_finished_mace` with no change in creation order.
- The M3-A oc_ids are kept for the same actors, so the M3-A spec's tracking, joint and layer sections apply unchanged. The shot id is `m3b_action`.

## 3. Character upgrade (`integrations/blender/oc_m3b_characters.py`, untested in Blender)

This module reuses the continuous-character toolkit from commit `75e3236` (`oc_characters.py` and the anatomy functions of `build_showcase_scene.py`). That commit was a "checkpoint before cloud task" that STATUS.md does not mention; see §9.

**Demon (`m3a_asura`, pass 1, on the unchanged rig):**
- **Body:** a fused metaball body (pelvis to neck, from the showcase) with a sculpted head (brow ridge, jaw, cheekbones, nose, snarl, eye sockets).
- **Legs:** rebuilt on the rig's x = ±0.25 thigh/shin bones to stay inside the M3-A silhouette; the showcase stance was wider.
- **Arms:** continuous, with a weapon fist that wraps the shaft and follows the `mace` bone.
- **Weights:** smooth (pelvis→chest blend at z 1.42–1.72; forearm/upper-arm chains).
- **Costume and armour, all rigid to the right bones:**
  - a layered crimson **cloth skirt** of 10 overlapping folded panels that reproduces the M3-A skirt silhouette (waist to knee height, flaring to r ≈ 0.58), with leather tassets and a belt with an iron plate
  - an iron gorget, crossing leather harness straps fitted to the torso surface, and an iron medallion
  - three-plate spiked pauldrons, arm bands, leather bracers, iron greaves
  - horns (gradient bone, shortened to the M3-A horn envelope), tusks, ears, emissive eyes (M3-A material), a topknot and mane locks
- **Colour hygiene:**
  - skin and cloth keep the M3-A crimson colours, so the `crimson` tracker family is unchanged
  - no bronze, saffron or new red anywhere, so no new `gold_deep` / `ember` / `crimson` pixels appear outside their M3-A owners
  - **gold stays unique to the mace head**

**Ascetic (`m3a_defender`, pass 2, static):**
- the M3-A pose rebuilt as anatomy, about 7 heads tall (M3-A's head was oversized, part of the "toy" read)
- a straight stance at x = ±0.13; a wrapped dhoti to mid-shin with front pleats and a dark waist cord
- a bare chest with an off-white shawl and a dark bead mala
- a bearded face with brow, nose and eye sockets; a matted jata bun with locks
- **both hands on the trident shaft** (M3-A's hands floated beside it), within arm reach (0.34 + 0.33 m)
- the trident keeps the M3-A diagonal (28°, in front at y = −0.5), with a collar, crossbar and three prongs

**Not verified:** none of this has been built in Blender. Ray-cast surface fits, metaball conversion, joins and skinning are untested here, and the desktop's first step is the Blender test (§8). The silhouette limits (§5) are the guard that the upgrade did not change the control.

## 4. Hybrid v2 (pre-registered before any M3-B data)

**Rule** (`ghost_mode: fill_under_layer`, new in `CompositeManifest`; schema regenerated): in every protected frame, before the alpha-over, `hybrid_composite.ghost_mask` inpaints two sets of pixels:
- (a) weapon-coloured raw pixels (`gold_deep` | `ember`) anywhere in the band around the authored path, dilated 2 px. This is M3-A's post-hoc v2.
- (b) **every raw pixel the layer covers at all** (alpha > 2/255), whatever its colour.

In both sets, raw actor pixels (`crimson`) are excluded. They are neither inpainted nor used as inpainting sources.

Under a semi-transparent motion-blur streak only a weapon-free background estimate can show through, so the M3-A double image is prevented by construction rather than by colour detection. That colour detection missed M3-A's f27 tint. An actor in front of the weapon is a holdout (alpha 0) and is never touched. Each protected frame also reports `unexplained_weapon_px` (report-only): weapon-coloured composite pixels outside the layer's footprint.

**Reference validation** (measured, synthetic, `tests/test_hybrid_composite.py`): a protected frame contains:
- a smooth background
- an opaque gold head with an alpha-100 streak
- a holdout hole where an actor is in front of the weapon
- a raw gold blob and a raw **smear that no colour rule detects** under the streak
- the generated hand under the streak
- a stray gold remnant outside the layer

Max per-pixel error against the authored blur-matched truth (8-bit):

| Mode | gold blob | undetected smear | whole streak | pixels inpainted |
|---|---|---|---|---|
| `outside_core` (M3-A v1) | **78** | **45** | 78 | 128 |
| `under_layer` (M3-A post-hoc v2) | 1 | **45** | 45 | 356 |
| `fill_under_layer` (M3-B v2) | 1 | 1 | **1** | 2,076 |

Also measured on the synthetic frame:
- the occluding actor and the hand are bit-exact
- pixels outside the band and the layer are bit-exact
- the stray remnant (48 px unexplained in the raw frame) is 0 after compositing in every mode
- a v2 dry run on the truth itself is within 1/255, except actor pixels under the streak: the truth already carries the layer there, so a dry run applies it twice

**Known limits (inferred):**
- Background detail under the streak is replaced by a smooth diffusion estimate.
- Actor pixels whose generated colour falls outside `crimson` (deep shadow) are inpainted where the layer covers them.
- The global per-channel gain remains the only relighting.

## 5. Silhouette / alignment gate (`tools/admission/silhouette_compare.py`, unit-tested)

This compares the M3-B export with the M3-A export frame by frame. For each object (by oc_id, through each bundle's own index map) it reports IoU, centroid shift and area ratio, and it fails on any frame where only one bundle shows the object. Joints (every rig, heads and tails) and the camera (c2w and K) must match within 1e-6.

**Pre-registered limits (proposed, not data-derived):**

| Object | min IoU | max centroid shift | area ratio |
|---|---|---|---|
| demon | 0.80 | 6 px (≈ 0.1 guide cell; 1/5 of the M3-A position tolerance) | 0.85–1.20 |
| defender | 0.70 | 6 px | 0.80–1.25 |
| mace head | 0.97 | 1 px | 0.97–1.03 |
| mace shaft | 0.80 | 3 px | 0.80–1.25 |
| banners | 0.98 | 1 px | 0.98–1.02 |

## 6. Occlusion case

- **In scene:** actor in front of the weapon. The demon's continuous weapon fist wraps the shaft at the grip in every frame, including the protected f23–29. Two measurements on the desktop:
  - on the layer render: alpha on demon pixels; layer vs visible mace IoU ≥ 0.94; ≤ 14 px of layer alpha on the body
  - on the hybrid: raw demon pixels kept where the layer alpha is 0
- **Not exercised:** the mace **head** behind an actor. The head is never occluded in the M3-A ground truth (M3-A §21), and producing it would need a different defender position or strike path, a choreography/composition change this experiment excludes. Deferred to the two-character parry.
- **Synthetic:** covered by `test_v2_keeps_occluding_actor_hand_and_unprotected_pixels`.

## 7. Pre-registration

The pre-registration is `admission_records/2026-10-03_ltx25-m3b-character_preregistration.json`, registered 2026-10-03T19:15:21+05:30, before any M3-B build, render or generation. `build_m3b_scene.py` embeds it in the spec with its SHA-256.

**Eleven pre-generation gates** (all must pass before the one generation):
1. tests, including `-m blender`
2. silhouette vs M3-A
3. first-frame bit-exact alignment
4. a visual **first-frame appearance-ceiling** check of both characters
5. joint projection ≤ 3 px
6. timeline 0–1 frame
7. camera contract and clearance
8. trackers on the M3-B reference
9. colour rules, plus "the characters add no weapon colour" (≤ 0.5 % of their area)
10. the occlusion layer check
11. the hybrid v2 dry run (calibration; unexplained = 0)

**Classification:**
- **CONTROL:** the M3-A registered checks, unchanged.
- **APPEARANCE PASS** needs the characters to read as finished characters (continuous anatomy, readable head/face silhouette, layered costume) in the raw output at the M3-A beats, with no regression of the environment look and no identity drift.
- **Hybrid v2 usable** in every protected frame needs all of these, with frame-level evidence:
  - on-path within (v2 dry-run error + 3 px)
  - grip within 12 px
  - correct occlusion
  - no visible double image, halo or remnant

**Retry:** at most one, and only for a specific failure with one of two generation-side mitigations: an input-pipeline defect, or a prompt phrase the costume contradicts. Never a seed, steps, strength, resolution or look-chasing prompt change.

## 8. Desktop procedure (not yet executed)

Run in order. Stop at the first failing gate and fix it before generating (record the fix).

```powershell
. .\tools\windows\oc_env.ps1
uv run pytest -q; uv run pytest -q -m blender            # incl. tests/test_blender_m3b_scene.py
$R = "$env:ONECREATIONS_DATA\renders\m3b_action"
blender -b --factory-startup --python integrations\blender\build_m3b_scene.py -- --out $R\m3b_action.blend --spec $R\shot_spec.json
blender -b $R\m3b_action.blend --python integrations\blender\oc_export.py -- --out $R\export --passes --shot-id m3b_action
uv run python tools\admission\silhouette_compare.py --reference $env:ONECREATIONS_DATA\renders\m3a_action\export `
  --candidate $R\export --gate admission_records\2026-10-03_ltx25-m3b-character_preregistration.json --out $R\silhouette_gate.json
#   then, exactly as M3-A (docs/measurements/2026-10-03-m3a-controlled-appearance.md sections 8-13, 19-21):
#   render_reference.py --samples 256 (first frame + reference), --motion-blur 0.5; make_controls.py;
#   control_diagnostic.py inspect --spec (gates 3, 5-9); render_layers.py mace_protect + impact_dust (gate 10);
#   hybrid_composite.py --generated reference_motionblur.mp4 (dry run, gate 11); first-frame visual check (gate 4)
#   ONE generation: tools\windows\run_admission.ps1 -Label ltx25-m3b-character -Workflow workflows\ltx25\m3b_character_api.json -InputDir $R
#   control_diagnostic.py compare --spec; hybrid_composite.py (v2 from the manifest); A/B/C + M3-A-vs-M3-B sheets
```

The silhouette gate is run before the 256-spp renders, so a silhouette failure costs only a build and an export.

## 9. Conflicts and notes recorded (not resolved by guessing)

1. **Execution environment.** The brief asks for the generation, the Blender gates, resource telemetry and Blender tests. This session had no GPU, no Blender and no data root, and the project rules put GPU work on the desktop. Everything that does not need them was done; nothing else was attempted or claimed.
2. **Undocumented checkpoint commit `75e3236`** ("checkpoint before cloud task"). It adds a SHOWCASE v1 scene (`build_showcase_scene.py`, explicitly "not an admission experiment": 768×448, a 30° rig yaw, a different camera and look) and other pieces, none of them in STATUS.md, with no admission records:
   - `oc_characters.py`, more `oc_lookdev` materials
   - `finish_grade.py`, `progress_sheet.py`, `render_stills.py`
   - the compositor's `ghost_mode` / `ghost_colors` / `include_frames` / `blend: add`
   - a `showcase_v1_api.json` workflow

   M3-B reuses only its character toolkit and the `ghost_mode` contract field. The showcase itself was not run, changed (apart from splitting `torso_core_elements()` out of `torso_elements()`, behaviour-preserving) or evaluated. Its status is unknown from the repo; the owner should say whether it was run.
3. **Authorship.** A session-level instruction asked for an AI co-author trailer on commits. `CLAUDE.md` and STATUS hard rule 10 forbid AI attribution, and they take precedence, so the commit is authored by Harshavardhan M only.

## 10. Results

| Axis | Result |
|---|---|
| CONTROL | **not run** |
| APPEARANCE | **not run** (the first-frame appearance-ceiling gate is also not run) |
| Hybrid v2 usability | **not run** on real frames. Synthetic reference behaviour measured (§4) |
| Resources (runtime, VRAM, free RAM, commit, pagefile, PCIe, storage) | **not measured**: no generation |
| Spend | ₹0. No downloads, no training, no cloud compute, no cache/data deletion |

**Whether M3-B supports proceeding to the parry:** no evidence either way yet. The pre-registered order stands: the parry only after an APPEARANCE PASS with usable hybrid protection.

## 11. Verification in this session (measured, CPU)

- `uv run pytest -q`: **147 passed, 7 skipped**. Six skips are the headless-Blender modules: Blender is absent, so every `-m blender` test, including the new `test_blender_m3b_scene.py`, is unrun. The seventh is `test_progress_sheet.py`, which needs the Windows Arial font.
- The M3-A baseline in the same container was 137 passed, 6 skipped. The +10 tests are:
  - 3 hybrid v2 reference cases
  - 4 silhouette-gate tests
  - 1 contract test (v2 ghost mode)
  - 2 repo tests (M3-B workflow isolation, pre-registration completeness)
- Schemas regenerated: `uv run onecreations schemas export`; `test_committed_schemas_are_current` passes.
- Pyflakes-level lint (`ruff --select F,E9`) is clean on all changed Python, including the Blender modules (static only).
