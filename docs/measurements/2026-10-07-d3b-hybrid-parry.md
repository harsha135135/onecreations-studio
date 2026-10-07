# D3(b) — Hybrid parry with ownership-aligned QC — 2026-10-07

**Question:** can LTX follow the two actors' synchronized choreography closely enough that the system can
automatically bind deterministic contact-critical weapon geometry to them and produce one readable, correctly timed
parry?

**Answer (pre-registered run `d3b_run1`): D3(b) FAIL. No final video was delivered.** The run executed unattended and
stopped by itself at POST_GENERATION_QC.

- **What failed:** the new attacker check `parry_contact_timing_v2` (a `fail` check). The generated attacker's hand
  region is a median 13.2 px from the authored grip over CONTACT−2…CONTACT+3 (limit 6), 26.4 px on a settled frame
  (limit 12), with a weak and flat timing signal (best lag +4 frames, NCC 0.44–0.58).
- **What passed:** the defender's reaction (`defender_reaction_timing`: median 3.0 px, ≤ 5.0 px on the settled frames,
  lag 0, NCC 0.75–0.99), the defender and attacker framing, the camera, the apex, and the deterministic 3-D contact.

By the ownership classification this is a failure of **generative attacker control (hand / grip at the bind)**. It is
not a failure of deterministic contact, protection, VFX, the compositor or QC execution. AUTONOMY is FAIL only because
its pre-registered PASS condition requires a delivered final.mp4; the execution itself was unattended and clean.

- **Pre-registration:** `admission_records/director/2026-10-07_d3b_preregistration.json`, committed and pushed in
  **`12162e7`** before the run.
- **Evidence:** `admission_records/director/2026-10-07_d3b_run1/` and `…/2026-10-07_d3b_instrument_validation.json`,
  `…/2026-10-07_d3b_rehearsal1.json`.
- **Media:** stays on `G:\onecreations\runs\d3b_run1` (not in Git).

## 1. D3(a): historical failure (unchanged)

`d3_run1` failed its pre-registered `contact_timing`, a check on the raw mace head reaching the mid-air contact. A QC
evaluator bug also crashed the first evaluation, and fixing it and resuming made AUTONOMY fail. Its pre-registration,
records and classification are untouched. Its ShotSpec still compiles to its archived CompiledShot with the v1 rule;
`test_d3a_compiled_shot_reproduces_with_its_v1_qc` holds that.

## 2. Why D3(a) remains FAIL

The criterion was pre-registered and the result did not meet it. D3(b) does not re-judge it; it is a new experiment.

## 3. Ownership mismatch discovered

D3(a) admitted the shot on the raw LTX mace head. The architecture already gives that geometry to Blender: P1
`fast_weapon_v2` replaces the mace in every frame. The admission QC therefore tested a component the pipeline does not
assign to LTX.

## 4. Hypothesis

LTX owns the actors. If the generated actors (bodies, hands, reaction timing) follow the authored interaction, the
deterministic weapon layers can reconstruct the authored contact, and the hybrid result is a correctly timed parry.

## 5. Ownership model (pre-registered, `ownership`)

- **Generative (LTX):** actor appearance, body motion, hand / grip motion, broad reaction timing, camera-conditioned
  appearance.
- **Deterministic (Blender, protected):**
  - mace geometry (P1) and trident geometry (P6)
  - the exact weapon contact (solved and verified before generation)
  - weapon continuity (protected layers in all frames)
  - holdouts
  - contact sparks and flash

It is expressed through the existing ProcessingPolicy (geometry = protected) and a new QC profile; no new framework.

## 6. New QC rule (`showcase_class_contact_v2`)

The contact action selects it (`mace_strike_blocked_v1.qc_profile`). All other shots keep `showcase_class_preflight_v1`
unchanged, so D2 and the guard-only prompt compile exactly as before (tests).

**`parry_contact_timing_v2` (fail) and `defender_reaction_timing` (fail).** The measurement, `check_grip_follow`:

- **Reference patch:** the actor's own pixels (object-index pass, weapon passes excluded) in a 49 × 49 box around the
  **projected authored grip** (weapon-bone head).
- **Search:** blurred greys, masked NCC over ±24 px. Colour-independent, like D2's QC.
- **Spatial:** median per-frame offset over the window ≤ 6 px.
- **Trajectory:** every frame of the settled sub-window ≤ 12 px (from CONTACT for the attacker; from CONTACT−2, the
  authored block arrival, for the defender), and median NCC ≥ 0.45.
- **Temporal:** the best lag (±4 frames, mean NCC over the whole window, including the approach) is within ±2 frames.
- **Windows:** attacker CONTACT−2…CONTACT+3 (approach and bind); defender `parry.GUARD_END`…CONTACT+3 (the raise and
  the bind).

## 7. Independent threshold derivation (frozen in `qc.GRIP_FOLLOW` / `ATTACHED`)

| Parameter | Value | Source |
|---|---|---|
| max_median_offset_px | 6 | D2 `contact_timing` max_offset_px (calibrated on Showcase v1 run 1 before D2, frozen in D2's pre-registration) |
| tol_frames | 2 | D2 `contact_timing` (M2-B timing tolerance) |
| search_frames / radius_px | 4 / 24 | D2 `contact_timing` |
| min_ncc | 0.45 | D2 `contact_timing` |
| max_offset_px (settled frames; attachment) | 12 | M3-A pre-registered attachment limit (projected grip vs generated hand) |
| final_weapon_contact | 2 px | the preflight 1 cm 3-D tolerance ≈ 1 px at ~7 m with f = 683 px, plus 1 px edge antialiasing |

**Not used:** D3(a)'s post-hoc "~1 px" grip observation (a weak nearest-crimson-pixel metric). The new instrument was
never run on `d3_run1` before the registration.

**Instrument validation on existing admitted material** (`…_d3b_instrument_validation.json`, thresholds unchanged):

| Material | Result | median px | settled max px | lag |
|---|---|---|---|---|
| D2 raw (admitted, control PASS) | pass | 5.25 | 5.4 | +1 |
| D2 raw, 4 frames late (negative) | fail | 12.35 | 18.4 | +3 |
| D2 raw, shifted 15 px (negative) | fail | 15.35 | 16.8 | +1 |
| D2 raw, time-reversed (negative) | fail | 17.7 | 19.2 | −4 |
| D2 final, attachment | pass | 5.8 | 6.7 | 0 |
| rehearsal (perfect stand-in), attacker / defender | pass | 0.0 | 0.0 | 0 |

One instrument design change came from this calibration, never from D3(a). On D2's raw the arm patch moves 12–29 px
in the smeared fast approach (M2-B) while the hold holds 4–5.5 px, and D2's final was visually attached there. So the
per-frame bound applies from the settled frames, while the approach still feeds the median and the lag. D2's admitted
raw sits at 5.25 px against the 6 px limit, so the calibration margin is small.

## 8. Raw-weapon diagnostic rule

D3(a)'s `contact_timing` became `raw_mace_contact`: same evaluator and parameters, `on_fail: diagnostic`. Recorded,
never decisive. `weapon_integrity` and `trident_integrity` stay repair evidence for the protection policies.
`decide()` lists diagnostic failures separately.

## 9. Deterministic contact requirement (unchanged)

Preflight `contact_geometry`: |gap| ≤ 1 cm at CONTACT, ≥ 0.30 m 4 frames earlier, no interpenetration (≥ −5 mm),
body clearance ≥ 0.10 m. Plus `contact_visible`. New final check: `final_weapon_contact`, where the delivered protected
layers touch on CONTACT…CONTACT+3 within 2 px.

## 10. Attachment QC

`mace_attached` and `trident_attached` (final): the same instrument on the delivered video, lag 0, per settled frame
≤ 12 px (M3-A), no appearance requirement. Body interpenetration is covered in 3-D by `contact_geometry`.

## 11. Defender QC

All D3(a) defender checks are kept: `defender_framing` (incl. the contact frame), `defender_stationary_root`,
`defender_weapon_axis`, `defender_weapon_visible`, `trident_integrity` (repair evidence), `trident_attached`. Added:
`defender_reaction_timing`.

## 12. Ghost-suppression decision: unchanged

The D3(a) post-hoc orange streak at f28 is the **protected mace layer's own authored 90°-shutter motion blur** (shown by
rendering the layer alone, at about 100 px/frame). It is not a raw ghost, so no ghost-suppression generalisation
applies. It is recorded as a known artifact, non-blocking.

## 13. Trident-gain decision: unchanged

The per-channel fit on a thin weapon picks up background: on D3(a)'s trident pixels raw/layer is 1.45/1.36/1.17, and
the fit clipped at 1.6. An owner-relative gain (Blender ref/layer on the weapon × raw/ref on the owner's eroded body) was
validated on existing material and **rejected**:

- **D2 mace:** it gives 1.23/1.38/1.6 vs D2's admitted fit 1.10/1.11/1.39.
- **Owner instability:** the ratio is unstable on the crimson owner's near-zero blue.
- **Trident:** it would still give ~1.3.

The fit is unchanged; this is recorded as a known artifact.

## 14. Pre-registration

`12162e7`, pushed before the run. It records the ownership, every QC check with its parameters and provenance, the
threshold sources, the instrument validation, the known artifacts and the acceptance classes. The generation policy:
one generation; a second only for an LTX technical failure or a failed `regenerate` check; never for repair or
diagnostic failures; no seed change; any post-generation fix invalidates autonomy.

## 15. Rehearsal (not a result)

`rehearsal_d3b_1` (`rehearse.py --raw reference`): **SUCCEEDED**, 729.7 s, all 15 stages.

- **Preflight:** 15/15.
- **Post-generation:** all pass on the perfect stand-in. Grip offsets 0 px, lag 0, for both actors.
- **Final:** all pass. Attachment 0 px; delivered layer gaps 0/0/1/0 px on the bind.
- **Clean execution:** every check evaluated with no error.

## 16. Exact prompt

> Create a cinematic shot of a horned Asura attacking an ascetic defender with a heavy mace in an ancient ruined
> temple at dusk. The defender parries the blow with a trident. Use a low orbit and push-in.

## 17. Exact command

`uv run onecreations generate "<prompt above>" --run-id d3b_run1`. The owner closed the browsers first; free RAM was
23.2 GB and the GPU idle. Launched 10:05:43, finished 10:11:33 IST, exit 1 (QC stop), no interaction after launch.

## 18. Raw LTX results

- **Attacker and defender bodies:** follow the authored motion. `subject_framing` NCC 0.74–0.95, ≤ 2.8 px;
  `defender_framing` NCC 0.73–0.98, ≤ 2 px including f29.
- **Camera and apex:** `camera_progression` NCC 0.80–0.995, ≤ 4 px; `apex_presence` pass.
- **Appearance:** as D3(a). The asura's armoured weapon arm becomes a bare crimson arm in the bind frames (§19).
- **Similarity to D3(a):** same seed, prompt and controls. The depth control is byte-identical to D3(a)'s; the first
  frame differs only by Cycles render noise. The raw is a separate file but very close to D3(a)'s.

## 19. Hand / grip results

**`parry_contact_timing_v2`: FAIL.**

| f | 27 | 28 | 29 (CONTACT) | 30 | 31 | 32 |
|---|---|---|---|---|---|---|
| offset px | 23.3 | 13.4 | 13.0 | 8.1 | 6.7 | 26.4 |
| NCC | 0.66 | 0.55 | 0.45 | 0.44 | 0.51 | 0.48 |

- **Spatial:** median 13.2 px (limit 6). **Trajectory:** settled max 26.4 px (limit 12). **Temporal:** best lag +4,
  but the lag curve is flat (NCC 0.44–0.58).

Visual, recorded as observation and not a re-judgement: in the reference the asura's armoured gauntlet closes on the
mace shaft. In the raw bind frames the generated weapon arm is a bare raised arm with a loose fist near, but not on, the
grip. So the generated hand does not hold the authored grip configuration. Part of the offset is the appearance
difference (the template is the armoured reference). This instrument's sensitivity to generated appearance is a
limitation, recorded in §30, not a reason to relax the result.

## 20. Raw weapon diagnostic

- **`raw_mace_contact`** (diagnostic): no onset within 6 px of the contact position; best NCC 0.454. As in D3(a).
- **`weapon_integrity`** (repair evidence): failed at f24/26/28/29.
- **`trident_integrity`** (repair evidence): failed at 19 frames (raw trident thin and unreliable).

## 21. Defender result

**`defender_reaction_timing`: PASS.** Median 3.0 px; settled frames (f27–32) ≤ 5.0 px; lag 0; NCC 0.75–0.99. Over the
whole raise the maximum is 13.4 px (f21, the lift), as expected for a moving limb. The defender's guard → lift → hanging
guard → bind is followed.

## 22. Deterministic weapon result

Preflight: `contact_geometry` pass (gap 0.0001 m at f29; no interpenetration; body clearance ≥ 0.21 m),
`contact_visible` pass, `defender_weapon_axis` pass, and `weapon_bone_projection` pass with f27 occlusion excluded and
reported. The deterministic contact was correct; it was never composited because the run stopped before REPAIR.

## 23–26. VFX, composite, final QC, parry readability

Not reached: REPAIR … DELIVER were `not_run`. There is no final video, so these cannot be assessed. No post-hoc
composite was made for D3(b).

## 27. Autonomy

**FAIL by the pre-registered wording.** Its first PASS condition is "one invocation produced deliverables/final.mp4 with
exit 0"; the run ended at QC with exit 1 and no final video. The execution itself was fully unattended: one
invocation, no manual Blender / ComfyUI / compositor / file / parameter action, no fix, no resume. QC executed with no
evaluator error, and the run ended by its own QC decision.

## 28. Resources (measured)

- **Wall time:** 349.5 s (BLENDER_BUILD 23.9, CONTROL_RENDER 241.1, FIRST_FRAME 18.3, PREFLIGHT_QC 7.7,
  LTX_GENERATE 48.1, POST_GENERATION_QC 10.4).
- **LTX job:** 38.7 s (load 3.6, text encode 9.1, denoise 20.7, VAE decode 3.6).
- **Memory:** peak VRAM 11,949 MB; minimum free RAM 2,079 MB; peak commit 76.0 %; pagefile +58 MB (from 60 MB).
- **PCIe:** gen4 x16 under load.
- **Storage:** d3b_run1 335 MB; G: 240,843 → 240,030 MB (including rehearsal_d3b_1).
- **Spend:** ₹0.

## 29. Classification (pre-registered)

| Class | Result |
|---|---|
| AUTONOMY | **FAIL** by wording (no final.mp4 / exit 1); execution itself fully unattended, no fix or resume |
| CONTROL | **FAIL**: `parry_contact_timing_v2` (attacker hand/grip). Defender reaction, framing, camera, apex and deterministic contact passed |
| PIPELINE | not reached (stopped by QC before REPAIR) |
| FINAL_INTEGRITY | not reached |
| PARRY_READABILITY | not assessable (no final video) |
| **D3(b)** | **FAIL**: no final video delivered |

**Ownership attribution of the failure:** generative actor control, specifically the attacker's weapon hand during the
bind. The generated arm loses the authored gauntlet and does not close on the authored grip.

**Not the cause:** defender reaction, deterministic contact, attachment, protection, VFX, compositor, QC
implementation; the AUTONOMY FAIL follows only from the missing delivery.

## 30. Limitations

- One run, one seed (seed policy unchanged from D3(a), as specified).
- The grip instrument compares the generated actor to the *authored appearance*. When LTX changes a limb's appearance
  (armour lost), offsets grow even if the hand is roughly in place. Its calibration margin on D2 is small (5.25 px vs
  6).
- The temporal criterion is weak when the generated region matches poorly (a flat lag curve).
- The defender instrument has no positive calibration on an admitted generation with a rigged defender. It passed here.

## 31. Conservative capability claim

None for a delivered parry. What D3(b) does show:

- The ownership-aligned QC executes autonomously and cleanly.
- LTX follows the rigged defender's reaction closely (≤ 5 px settled, on time).
- The deterministic contact is exact before generation.
- The generated attacker's weapon hand at the moment of the block is the component that does not meet the frozen
  control tolerance in this shot class.

## 32. Proposed next milestone (owner decides)

**D4 (proposed): attacker weapon-arm fidelity at contact**, before any new action or camera. Options, each a new
pre-registered experiment:

- (a) Strengthen the arm's appearance in the conditioning: a first frame and costume where the weapon arm's armour
  reads as one solid shape. LTX dropped the gauntlet. The M3-A rule says the first frame is the appearance ceiling.
- (b) Make the attacker's hand and forearm part of the protected layer during the bind (extend ownership by one
  component, the gripping hand), with its own attachment QC to the generated arm.
- (c) Choreography: the D3(b) brief excluded changing it. A slower final approach was the other D3(a) option and stays
  open for the owner.
