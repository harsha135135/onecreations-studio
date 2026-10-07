# D3(a) — Reactive parry: one mid-air block, prompt → final video — 2026-10-07

**Question:** can a supported prompt that asks for a parry produce, through the unchanged one-command pipeline, a
final video in which the defender reacts and blocks the mace on his trident with a weapon-on-weapon contact on the
authored frame?

**Answer (pre-registered run): D3 FAIL — no final video was delivered.** `d3_run1` ran one LTX generation. The run
then stopped at POST_GENERATION_QC, first with an evaluator crash (a bug, §11), and, once that was fixed and the stage
was resumed on the same generation, with the pre-registered `contact_timing` check failing. The raw generated mace head
never reaches its mid-air contact position: its best match is 24–31 px away, NCC ≤ 0.43. Everything else that the
pre-registration calls CONTROL passed on the raw generation, including the new `defender_framing`
(NCC 0.69–0.98, ≤ 2 px, contact frame included). The deterministic parry (engine, contact solve, protection, QC wiring)
is complete and tested.

A **post-hoc diagnostic**, labelled and not a result, composited the same raw with the policy layers (§13). The
generated asura's hand sits within ≤ 1 px of the authored grip on every bind frame. The repaired video reads as a
parry.

Pre-registration: `admission_records/director/2026-10-07_d3_preregistration.json`, committed and pushed in `83e41ee`
before the run. Evidence: `admission_records/director/2026-10-07_d3_run1/` (request, plan, spec, compiled shot,
execution record, QC, LTX monitor record and telemetry, media hashes,
post-hoc summary; the console logs of the run and the resume sit beside them locally, gitignored like D2's), `…/2026-10-07_ascetic_defender_v2_admission.json`, `…/2026-10-07_d3_rehearsal1.json`. Media stays
on `G:\onecreations\runs\d3_run1`, `…\d3_run1_posthoc` and `…\rehearsal_d3_1` (not in Git).

## 1. Starting state and owner decisions

D2 (`2b2454a`, 195 tests) delivered a prompt → final video for the Showcase class. Its own limitations (D2 doc §28)
were a static, unrigged defender whose trident is fused into its mesh, and a mace that lands on the floor about 1.1 m
short of him. Owner decisions this session:

- **Milestone:** D3(a), the reactive parry.
- **Contact:** a **mid-air block**, the downswing stopped on the raised trident, with one synced CONTACT.
- **Effects:** default parry FX are **sparks + a light-only flash at the 3D contact point**, with no ground dust or
  cracks unless the prompt asks for them.

## 2. What was built

| Area | Change |
|---|---|
| Rig builder | `RigProfile` in `build_temple_strike_scene.py`. Behaviour-neutral: M2-B, M3-A and Showcase rebuild with **bone matrices identical (max difference 0.0)**. The only mesh difference is one asura vertex at 2.4e-7 m, float32 noise. |
| Defender | `ascetic_defender_v2` (`build_defender_v2`): v1's body, dress and hair in a rest pose on a 16-bone rig with the M2-B topology and the ascetic's proportions; the arms are separate meshes on chain weights; the fists are rigid to the trident. |
| Trident | `trident_v2` is its own object `sc_trident` (pass 10). The shaft is 0.035 m (v1: 0.022 m, about 4–5 px at 768). |
| Actions | `mace_strike_blocked_v1` (attacker) is the slam's guard, wind-up and apex. The contact pose is **solved against the defender's block**, so the head touches the shaft on CONTACT by construction. A 4-frame bind follows, then a rebound and a re-chamber. `trident_parry_v1` (defender): guard → lift to vertical (clear of the wind-up) → hanging guard 2 frames before the blow → bind → push → high ready. Keys are on every frame from interpolated hand-midpoint targets, so both hands stay on the shaft. |
| Director | Role-filtered actions; a parry word selects the pair and the rigged defender variant; partner pairing and `strike_frames` sync; `SPEC_SYNC_CONTACT` / `SPEC_CONTACT_PARTNER`; engine combinations; ActionTimeline `contacts`; P6 `contact_weapon_v1`; `clash_flash_v1`. |
| Compositor | Optional colour rule; joints per protected layer; `ProtectionRule.ghost_frames` (`all` for a long thin weapon). |
| QC | Preflight: `contact_geometry`, `contact_visible`, `defender_stationary_root`, `defender_weapon_axis`, `defender_weapon_visible`; `weapon_bone_projection` excludes and reports occluded frames for contact shots. Post-generation: `defender_framing`, `trident_integrity`. Declared checks without an evaluator now raise. |
| Fixes | A named defender ("Shiva") produced a timeline the engine contradicted (role `defender` hard-coded); found by reading, fixed with a building test. `contact_timing` crashed when no frame qualified (found by d3_run1; §11). |

## 3. The parry as authored (engine, measured)

The contact is solved, not hand-tuned. The engine evaluates the defender's block pose, takes the shaft point 1.10 m
from the rear hand, and places the mace-head centre on the shaft's upward normal. It then iterates until the head's
nearest vertex is exactly one shaft radius from the axis (solve gap 1e-4 m).

Per-frame vertex distances recorded in the spec:

- **Head to shaft:** 0.0001 m on the 4 bind frames (29–32); ≥ 0.30 m 4 frames before contact; never below 0.
- **Clearance after the bind:** 0.025 m as the two weapons part.
- **Bodies:** trident to attacker ≥ 0.33 m; mace head to defender ≥ 0.21 m.

This holds at strike_frames 2, 6 and 9 (Blender tests at 6 and 9).

Staging was found by measurement, with three rounds:

1. **Trident pointing at the attacker:** rejected because it lies parallel to the mace in the image. The hanging
   guard was chosen instead: the weapons cross at ~70° on screen.
2. **Raise path:** the asura's existing wind-up sweeps through the guard trident's tip (−2 to −3 cm; D2 has the same
   geometry with the thinner shaft). Starting the raise earlier was not enough. A two-stage reaction fixed it: lift the
   trident to vertical and back, then bring it over while the mace is at the apex.
3. **Interpenetration and framing:** the defender's push lifted the shaft into the rebounding mace (−1.2 cm), and the
   first rebound threw the mace head out of frame. A forward push one frame after the mace leaves, plus a lower
   rebound, fixed both.

The blocked strike's mace is measured at **1.51 head widths/frame** into contact (103.7 px/frame, head 68.7 px; the
same probe gives 1.278 for the Showcase slam vs the registered 1.27). So P1 protects the mace as in D2, and P6 protects
the trident.

## 4. Defender admission (deterministic, before LTX)

v1 and v2 were built in the D2 shot with the held guard and exported with passes, with Cycles stills at frames 1 and
30:

- **Silhouette IoU** (v2 pass 2 ∪ trident pass 10 vs v1 pass 2): **0.943 / 0.935**.
- **Attacker joints:** max difference **0.0 m**.
- **Skinning:** 62,409 vertices, **0 unweighted**, max weight-sum error 8.3e-5.
- **Visual:** the same stance, trident line and hand positions; the shaft reads thicker; no clipping seen.

The admission rule was not pre-registered: admit unless the guard diverges visibly. Decision: **ADMIT**.

## 5. Preflight (d3_run1, measured): 15/15 pass

- **D2 checks:** all pass. Weapon bone 2.11 px on visible frames. Frame 27 is excluded and reported: the head is 38 %
  visible behind the asura's own horn and pauldron, 5.63 px; this is real occlusion, and the composite reproduces it.
  Camera 4.7e-7 m; clearance 1.95 m.
- **`contact_geometry`:** gap 0.0001 m at f29; 1.43 m at f25; min 0.0001 m; body clearance 0.213 m.
- **`contact_visible`:** contact at (430, 216) px, both weapons within 16 px.
- **Defender:** stationary root 0.0 m; trident axis median 2.14 px; trident ≥ 1,185 px in frame.

## 6. Rehearsal (not a result)

`rehearsal_d3_1` ran every stage with the run's own sharp Blender reference standing in for LTX
(`rehearse.py --raw reference`; new in D3, since no earlier parry generation exists).

- **Outcome:** **SUCCEEDED**, 718.7 s, all 15 stages; REPAIR rendered both protected layers in 358 s.
- **QC:** post-generation all pass, final QC 5/5.
- **Scope:** it proves wiring, layers, contact-keyed effects and delivery, not QC thresholds (the stand-in is
  perfect).

## 7. Exact prompt and command

> Create a cinematic shot of a horned Asura attacking an ascetic defender with a heavy mace in an ancient ruined
> temple at dusk. The defender parries the blow with a trident. Use a low orbit and push-in.

`uv run onecreations generate "<prompt above>" --run-id d3_run1`. The owner closed Chrome first; free RAM was 23.5 GB.

## 8. Planner interpretation

- **Cast:** asura_v2 (prompt "horned asura"); **ascetic_defender_v2** (prompt "defender"; the rule swapped it in
  because trident_parry_v1 needs a rigged defender).
- **Actions:** trident_parry_v1 (prompt "parries"); attacker action **mace_strike_blocked_v1** (rule: the parry's
  partner; the prompt's "attacking" first selected the slam).
- **Weapons:** heavy_mace_v1 (prompt "mace"); trident_v2 (prompt "trident").
- **Camera and look:** orbit_push_v1 low; mythic_temple_dusk_v1.
- **Effects:** sparks_v1 + clash_flash_v1 (the blocked strike's default package).
- **Protection:** MACE → fast_weapon_v2 (P1, 1.51 ≥ 0.7); TRIDENT → contact_weapon_v1 (P6).
- **Events:** strike.CONTACT = parry.CONTACT = 29.

## 9. LTX result (measured)

One generation, attempt 1, no retry. The profile, workflow and seed are unchanged from D2.

- **Timing:** stage 73.4 s; ComfyUI job 39.4 s (load 3.8, text encode 9.5, denoise 20.7, VAE decode 3.5).
- **Memory:** peak VRAM 11,943 MB; minimum free RAM 2,057 MB; peak commit 75.5 %; pagefile +20 MB.
- **PCIe:** gen4 x16 under load.

## 10. Post-generation QC (measured; after the fix in §11)

| Check | Result |
|---|---|
| video_valid | pass |
| subject_framing | pass: NCC 0.74–0.95, ≤ 2.8 px |
| **contact_timing** | **fail** (`on_fail: fail`): no frame within 6 px of the contact position; best NCC 0.433 at offsets 24–31 px |
| apex_presence | pass: NCC 0.563, 4.1 px |
| weapon_integrity | fail at f24/26/28/29 → repair (policy) |
| camera_progression | pass: NCC 0.79–0.995, ≤ 4 px |
| output_integrity | pass |
| **defender_framing** (new) | **pass**: NCC 0.69–0.98, ≤ 2 px at f0/12/24/**29**/36/48 |
| trident_integrity (new) | fail at 22 frames → repair (policy) |

Decision: **fail** (`contact_timing`). The repairs were scheduled by policy, with QC evidence attached per weapon. The
run stopped as pre-registered.

**What the raw shows** (contact sheets vs the reference):

- **Defender:** LTX follows the defender's whole reaction: guard, lift to vertical at f13, hanging guard from f26,
  push and ready.
- **Asura:** the strike's arm motion is on time.
- **Mace head:** in the bind (f29–33) it is a hallucinated spiky gold blob near the shaft with most of its own shaft
  missing.

This is the M2-B fast-weapon failure (1.51 head widths/frame into contact) carried into a contact that, unlike the
slam's floor contact, gives the head nothing to rest on for six frames.

## 11. The evaluator crash (bug) and the resume

The first invocation stopped with `ValueError: min() iterable argument is empty` in `check_contact_timing`. The code
took the onset as a `min()` over frames meeting the criteria, and no frame did. D2's raw always had one, so the path had
never run.

- **Fix:** no onset is a failed check (`observed_onset: None`), plus a regression test.
- **Resume:** `--resume … --from-stage POST_GENERATION_QC` re-evaluated the same cached generation (LTX and Blender
  cached) and recorded the verdict above.

By the pre-registration this resume makes **AUTONOMY: FAIL**, independent of the QC verdict. Both console logs are
archived.

## 12. Classification (pre-registered)

| Class | Result | Why |
|---|---|---|
| AUTONOMY | **FAIL** | the first invocation crashed in QC (bug); a code fix and a resume were needed to obtain the verdict |
| CONTROL | **FAIL** | `contact_timing` (a `fail` check) failed; all other CONTROL checks passed, incl. `defender_framing` |
| PIPELINE | not reached | REPAIR … DELIVER not run |
| FINAL_INTEGRITY | not reached | no final video |
| PARRY_READABILITY | not assessable | no final video (see §13 for a post-hoc look) |
| **D3** | **FAIL** | no final video was delivered |

## 13. Post-hoc diagnostic (not a result)

The rehearsal rendered the protected and effect layers from the identical scene: same object-index pass and joints,
normals within 3e-6. Those layers were composited over d3_run1's raw with the pipeline's own functions
(`hybrid_composite.run`, `finish_grade.run`) into `G:\onecreations\runs\d3_run1_posthoc`.

- **Hand vs grip:** the projected authored grip lies **≤ 1 px from the generated asura's hand on every bind frame**
  (10 px at f28, the fastest arrival frame).
- **Gains:** mace 1.11/1.11/1.08; trident 1.6/1.6/1.25, at the clip limit (the composited trident reads slightly
  silver).
- **Effects:** start at f29.

**Visual:**

- The final reads guard → lift → hanging guard → mace lands on the shaft with sparks and flash → bind → rebound →
  re-chamber.
- One orange motion-blur streak at f28, as in D2 f26.
- A faint raw remnant above the mace head at f29.
- The shaft passes in front of the defender's face during the block.

So `contact_timing`, as designed for D2's floor slam, measures the raw weapon head, which the policy replaces in every
frame. For a mid-air contact it fails while the generated arm is on time. Whether to change that rule is an owner
decision (§16), and it can only be judged by a new pre-registered run.

## 14. Performance and storage (measured)

- **d3_run1 to the stop:** first invocation 368.4 s (CONTROL_RENDER 240.1 s, BLENDER_BUILD 23.8 s, FIRST_FRAME 18.4 s,
  LTX 73.4 s).
- **Rehearsal:** 718.7 s.
- **Storage:** d3_run1 335 MB, d3_run1_posthoc 95 MB, rehearsal_d3_1 478 MB; scratch builds stayed in the session
  scratchpad. G: free 241,750 → 240,843 MB.
- **Spend:** ₹0.

## 15. Limitations

- One run, one seed; the raw mace failure in the bind is one observation (consistent with M2-B / 768 / M3-A / Showcase /
  D2 fast frames).
- The parry is one line (hanging guard). The contact point on the shaft is fixed (1.10 m from the rear hand). The
  defender's root and legs never move.
- `defender_framing` at the contact frame is the only raw check of the defender's block. A trident template check is
  replaced by masked NCC (`trident_integrity`), which is evidence for repair, not a timing check.
- The rehearsal's stand-in is perfect: it cannot test QC thresholds.

## 16. Next (proposed, owner decides)

1. **D3 run 2**, pre-registered with **one rule change**. For a shot with a declared weapon contact whose weapons are
   both policy-protected, `contact_timing` measures the **generated hand at the authored grip** (the post-hoc grip
   metric, threshold to pre-register, e.g. ≤ 6 px on CONTACT…CONTACT+3) instead of the raw weapon head. The head check
   becomes repair evidence. One generation (same seed and profile), ₹0.
2. Or keep the rule and make the raw head hold: a longer bind or a slower final approach, so the raw head can settle.
   This changes the choreography, and M2-B suggests the speed into contact is the cause.
3. Either way: lower the trident gain clip, or calibrate the trident gain on its own pixels; and decide whether the
   shaft crossing the defender's face is acceptable.
