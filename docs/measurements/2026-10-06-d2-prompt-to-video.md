# D2 — One-command prompt → final video — 2026-10-06

**Question:** can a supported natural-language request execute the complete existing OneCreations production
pipeline automatically (no manual Blender, ComfyUI or compositor interaction, no manual stage invocation) and produce
a validated final MP4?

**Answer: yes, for the Showcase class. D2 PASS** (AUTONOMY, CONTROL, PIPELINE and FINAL INTEGRITY all PASS against
the rules pre-registered in `admission_records/director/2026-10-06_d2_preregistration.json`, committed in `2fd0226`
before the run). One invocation of `onecreations generate "…"` ran all 15 stages in 514.2 s (measured) with one LTX
generation and no retry, and delivered `final.mp4`. Appearance is reported separately: **IMPROVED** for the attacker
(asura_v2), otherwise Showcase-comparable.

Evidence (small JSON, in Git): `admission_records/director/2026-10-06_d2_run1/` (request, plan, spec, compiled shot,
execution record, QC, LTX monitor record and telemetry CSV, report, media hashes, console log),
`…/2026-10-06_asura_v2_admission.json`, `…/2026-10-06_d2_rehearsal1.json`. Media stays on
`G:\onecreations\runs\d2_run1` and `G:\onecreations\renders\asura_v2_admission` (not in Git).

## 1. D1 starting state

D1 (`40fb6b4`, 180 tests) took a supported request to a validated ShotSpec and CompiledShot, and automatically built
the Blender scene, controls, first frame, masks and preflight QC (10 checks passed). `generate` refused without
`--dry-run` / `--preflight`: prompt → final video had not been demonstrated. Showcase v1 (`b30dad6`) was the
strongest complete video, produced by manually invoked tools.

## 2. D2 architecture

D2 adds orchestration, automatic QC, policy-driven repair and delivery on top of D1's layers, reusing every proven
tool unchanged in behaviour:

| New / changed | File | Role |
|---|---|---|
| Executor | `src/onecreations/director/pipeline.py` | 15-stage graph, content keys, resume, failure handling, run record, report |
| Video QC | `src/onecreations/director/video_qc.py`, `media.py` | post-generation checks A–F and final integrity checks (measurable only) |
| QC profile | `director/qc.py` | post-generation + final checks implemented; `on_fail` action as data |
| CLI | `onecreations generate "PROMPT" [--output ROOT] [--run-id ID] [--resume DIR] [--from-stage S]` | real execution; `--dry-run` / `--preflight` unchanged |
| Character | `build_showcase_scene.py:build_asura_v2`, registry `asura_v2` | upgraded attacker, same rig/anchors/ids (§6) |
| Material pass | `oc_export.py --material-index`, `ExportPasses.material_index_map` | per-part masks (§9) |
| Masks | `executor.write_masks` | object masks + per-part masks (object AND material index) |
| Admission tool | `tools/admission/character_admission.py` | deterministic character comparison |
| Rehearsal | `tools/director/rehearse.py` | all stages except LTX (stand-in raw), before spending a generation |

Every stage reads the CompiledShot or upstream outputs only; there is no configuration outside it.

## 3. Executor

`pipeline.execute(run_dir, request, options)` writes `request.json` once (a run directory's request is immutable),
then runs the stages in order. Options are fixed defaults recorded in `execution.json`: first frame 1024 spp,
references 64 spp, OptiX, LTX RAM guard 20 GB free, one technical LTX retry, LTX timeout 3600 s. The command prints
every stage and exits 0 only when DELIVER ran after FINAL_QC passed.

## 4. Stage graph

`PLAN → VALIDATE → COMPILE → BLENDER_BUILD → CONTROL_RENDER → FIRST_FRAME → PREFLIGHT_QC → LTX_GENERATE →
POST_GENERATION_QC → REPAIR → VFX → COMPOSITE → GRADE → FINAL_QC → DELIVER`

Each stage record holds `id, key, status, started, finished, duration_s, outputs {path, sha256}, info, failure`.
Statuses: `done`, `cached`, `failed`, `retried`, `superseded`, `not_run`. A failure stops the run; all later stages
are recorded `not_run`, and the report says "Not delivered" with the stage and reason (tested). The tools run per
stage are listed in `docs/runbooks/prompt-to-video.md`.

## 5. Resumability

A stage's key is `content_hash({stage, pipeline version, inputs})`. The inputs are the CompiledShot sections it
consumes plus the SHA-256 of the upstream outputs it reads (`pipeline.stage_inputs`). On `--resume` a stage whose key
matches and whose recorded outputs still hash the same is `cached`. So a failed GRADE reruns only GRADE (and what
follows if its output changes); LTX and Blender never rerun for a late failure. A byte-identical regenerated output
leaves the downstream keys unchanged, and a changed spec section invalidates exactly its dependants (tested:
`test_resume_skips_unchanged_stages_and_reruns_only_invalidated_ones`). The real run needed no resume.

## 6. Character asset version used

**asura_v2** (new registry asset; `asura_showcase_v1` kept unchanged as the fallback and still selectable as
"showcase asura"; the archived Showcase ShotSpec still builds v1). Built in ~1 h in the priority order of the brief:
- firmer, less-blended muscle fields (stiffness 2.7, size compensated), metaball resolution 0.016 → 0.011 (torso) /
  0.010 (arms), 8 smoothing iterations
- a 1.12× head with a nose bridge and horn bases fused into the skull; longer horns; 9 mane locks
- an iron breastplate tied to the pauldrons by leather shoulder straps, bronze plate rims, gorget, knee guards
- finger tubes wrapped around the mace grip (rigid to the mace bone); a closed off-hand fist

**Admission** (deterministic, before LTX; both builds of the Showcase shot, Cycles 128 spp at opening f4, apex f23,
fast strike f25, contact f29, recovery f40; `oc_export --passes`; measured):

| Proxy (per frame, v1 → v2) | f4 | f23 | f25 | f29 | f40 |
|---|---|---|---|---|---|
| silhouette solidity (lower: forms separate) | 0.580 → 0.564 | 0.528 → 0.515 | 0.505 → 0.497 | 0.489 → 0.479 | 0.498 → 0.485 |
| outline perimeter/√area | 14.21 → 14.86 | 12.56 → 13.12 | 13.07 → 13.87 | 13.84 → 14.67 | 13.84 → 14.76 |
| crease fraction (normal pass, > 12°) | 0.441 → 0.473 | 0.450 → 0.485 | 0.445 → 0.479 | 0.429 → 0.469 | 0.430 → 0.463 |
| hand pixels on the shaft (≤ 2 px) | 94 → 164 | 75 → 132 | 105 → 178 | 113 → 161 | 62 → 120 |

Rig motion identical (`joints.npz` max difference 0.0 m), pass indices identical, skinning valid (0 unweighted,
max weight-sum error 9.5e-5), every character pixel in a material group. Visual: one defect found and fixed (the
off-hand fingers wrapped an empty grip and read as a hook); no severe clipping or broken joints seen. The proxies were
chosen with the comparison, not pre-registered; the rule applied was "all improve at every frame, rig identical".
Decision: **ADMIT**; recorded in the registry and in the run (`scene_build.attacker_asset = asura_v2`).

## 7. Post-generation QC

Colour trackers are invalid under the warm grade (Showcase), so every check matches blurred-grey templates from the
Blender reference render against the generated frames, located by the object-index pass. Each check carries its
failure action as data:

| Check (brief item) | Measures | on_fail |
|---|---|---|
| `video_valid` (A) | decodes, 49 frames, 768×448, no blank (std < 3) or abrupt (> 25 abs and > 6× median) frames | regenerate |
| `subject_framing` (B) | attacker template at f0/12/24/36/48: NCC ≥ 0.5, offset ≤ 32 px | fail |
| `contact_timing` (C) | weapon-head onset at the ground within ±2 frames of `strike.CONTACT` | fail |
| `apex_presence` (C) | weapon head at `strike.APEX` (NCC ≥ 0.4, ≤ 10 px) | fail |
| `weapon_integrity` (D) | weapon head APEX..CONTACT (NCC ≥ 0.4, ≤ 10 px): the raw fast-weapon failure detector | repair |
| `camera_progression` (E) | background registered to the authored move at the checkpoints (NCC ≥ 0.5, ≤ 24 px) | fail |
| `output_integrity` (F) | black-hole fraction ≤ 0.5 % | regenerate |

Thresholds were calibrated on Showcase run 1 before D2 and frozen in the pre-registration. Subjective review (does
the strike read, cinematic quality) is recorded separately (§22–26), never as a score.

## 8. Repair policies

`decide()` never asks QC whether to repair: the CompiledShot's ProcessingPolicy for MACE is `geometry=protected`
(rule `fast_weapon_v2`, P1), so REPAIR is scheduled from the policy, and the `weapon_integrity` result is attached as
evidence. The Showcase weapon repair is now the registered `fast_weapon_v2` rule consumed through the semantic object
(ASURA's MACE → its parts and pass indices from the registry), not an object name in a script. It owns: protected
frames (all), the authored Blender mace layer, 90° motion-blur shutter, hand/body holdouts, depth occlusion,
`swept_band` raw-ghost region, temporal-neighbour fill with deterministic diffuse fallback, colour/softness matching
(per-channel gain from the reference, `soften_px`) and the final integrity checks (§13).

## 9. Masks

`write_masks` writes one mask per semantic object (object-index pass) at f0, APEX, CONTACT and the last frame (12
objects in this run). New: a character entry may declare `material_masks`; `asura_v2` declares skin 1, armour 2
(iron, bronze), cloth_harness 3 (leather, loincloth), head_details 4 (horn, tusk, eye, hair); the mace head (gold) is
group 5 and is also its own object. With `--material-index` the export adds the Cycles IndexMA pass, and a per-part
mask is object AND material index (tested). In the admission export the parts cover the whole asura (e.g. f29: skin
11,004 px, armour 11,725, cloth/harness 4,627, head details 2,901, unassigned 0). The defender and trident remain
one object index (registry limitation). No masked editing is implemented.

## 10. VFX event propagation

Every effect is a ShotSpec event triggered by `strike.CONTACT` (offset 0). The compiler resolves CONTACT = APEX +
strike_frames = 29 (0-based) and emits one `impact_fx` effect layer whose trigger is the ActionTimeline phase edge
`strike→impact`. The VFX stage turns that edge into Blender frames 30–49 (`_effect_frames`), the builder's `fx`
components are dust, debris, sparks and cracks, and no stage contains a literal 29 (a slow strike moves everything to
33–49; tested). No flash or jolt was requested, so none was compiled.

## 11. Compositing

Two passes of the proven `hybrid_composite`: REPAIR applies the `protected_geometry` layers to the raw LTX video
(`repair/repaired.mp4`), COMPOSITE applies the `effect` layers to that (`composite/composite.mp4`), each with holdout
occlusion. Recorded order: **raw → mace_protect → impact_fx → grade**. Intermediates are kept for debugging; the
user-facing output is `deliverables/final.mp4`.

## 12. Grade

The ShotSpec's `grade.preset` (`showcase_v1`, a registry default for this class) is compiled into
`CompiledShot.grade`; GRADE passes it to `finish_grade.py` unchanged. Filter chain recorded in the run: contrast 1.05,
colour balance, vignette 0.45, unsharp 0.35, grain seed 1000; shake none.

## 13. Final QC

| Check | Rule |
|---|---|
| `final_valid` | final master exists and decodes, 49 frames, 768×448, no blank or abrupt frames |
| `protected_weapon_present` | Blender mace template in the final at every protected frame (NCC ≥ 0.7) |
| `effects_begin_at_contact` | first frame whose effect region changes ≥ 8 levels is CONTACT; ≤ 2 before it |
| `bounded_repair` | repaired − raw changes ≤ 0.1 % of pixels outside the weapon pass ∪ 10-px band |
| `no_holes` | black-hole fraction ≤ 0.5 % |

The final hash is recorded (`qc/final.json`, `execution.json`, `report.json`).

## 14. Delivery format

`G:\onecreations\runs\<run_id>\`: `request.json director_plan.json shot_spec.json compiled_shot.json execution.json
preflight/ controls/ generation/ repair/ vfx/ composite/ grade/ qc/ deliverables/{final.mp4, preview.mp4,
report.json, report.md}`. `preview.mp4` is Blender reference with effects | raw LTX | final at half scale.
d2_run1 occupies 442 MB.

## 15. Exact prompt

> Create a cinematic shot of a horned Asura attacking an ascetic defender with a heavy mace in an ancient ruined
> temple at dusk. The defender guards with a trident. Use a low orbit and push-in. Add dust, debris, sparks and floor
> cracks on impact.

Command (from the repo, PowerShell/Git Bash):
`uv run onecreations generate "<prompt above>" --run-id d2_run1`

## 16. Planner interpretation

`keyword_v1`, supported, no warnings, nothing unsupported. Decisions (source, evidence): environment
temple_courtyard_v1 (prompt, "ruined temple"); attacker **asura_v2** (prompt, "horned asura"); defender
ascetic_defender_v1 (prompt, "defender"); attacker weapon heavy_mace_v1 (prompt, "mace"); defender weapon trident_v1
(prompt, "trident"; integrated into the defender asset); actions mace_slam_v1 (prompt, "attacking") and
defender_guard_v1 (prompt, "guards"); camera orbit_push_v1 (prompt, "orbit"), variant low (prompt, "low"); look
mythic_temple_dusk_v1 (prompt, "dusk"); VFX impact_dust_v1, debris_v1, sparks_v1, floor_cracks_v1 (prompt);
protection MACE → fast_weapon_v2 (rule P1). "cinematic", "heavy" and "ancient" select nothing (the only mace is heavy;
the only temple is ancient).

## 17. Defaults and rules

Rule: P1 fast_weapon_v2 for MACE. Registry/planner defaults (not choices the prompt made, and in D1's plan format not
listed as decisions — a known gap): 49 frames at 24 fps, 768×448, generation profile `ltx25_union_768_v1`, seed 1000,
grade `showcase_v1`, compositing `protected_layers_v1`, QC profile, camera target ASURA + (1.3, 0.1, 1.5) m, default
placements and strike timing (strike_frames 6), action parameters empty.

## 18. Preflight result

10/10 passed (measured): events resolved (APEX 23, CONTACT 29); timeline matches the engine; weapon-bone projection
≤ 2.11 px; stationary root 0.0 m; camera contract 4.7e-7 m / 3.8e-5°; clearance 1.95 m; actors in frame (asura ≥
25,705 px, defender ≥ 7,800 px, no border contact); mace head ≥ 2,471 px; depth valid (21 isolated background px);
first frame aligned by construction.

## 19. LTX result

One generation, attempt 1, no retry, no regeneration. LTX-2.5 22B distilled INT8 ConvRot + Union IC-LoRA (ComfyUI),
768×448×49, seed 1000, 8 steps, first-frame conditioning on `controls/first_frame.png`, Union depth control
`controls/depth_control.mp4`; workflow compiled from the CompiledShot (`generation/workflow_api.json`, SHA in the
monitor record). Stage 49.3 s including ComfyUI start 7.6 s; ComfyUI job 39.9 s (load 3.7, text encode 8.9,
denoise 21.8 with first step 14.0 s and median 1.00 s, VAE decode 3.6). Free RAM before 22.2 GB.

Post-generation QC (measured):

| Check | Result |
|---|---|
| video_valid | pass: 49 frames, 768×448, no blank/abrupt frames |
| subject_framing | pass: NCC 0.77–0.95, offsets ≤ 2.8 px |
| contact_timing | pass: onset f29 = CONTACT (0 frames) |
| apex_presence | pass: f23, NCC 0.53, 8.0 px |
| weapon_integrity | **fail at f24, f26, f27** (offsets 10–16 px; raw mace head lost in the fastest frames, as in every earlier run) → repair (already scheduled by policy) |
| camera_progression | pass: NCC 0.82–0.995, ≤ 4 px |
| output_integrity | pass: no holes |

Decision: **proceed**, repair MACE (policy).

## 20. Repair result

`mace_protect` rendered for all 49 frames (swept_band ghost region, temporal fill, per-channel gain 1.10 / 1.11 /
1.39). Visual: in the raw output the mace head disappears at f25–f27; in the final it is solid, attached to the
hand and on time through the strike. `bounded_repair`: 0.0 % changed outside the weapon band.

## 21. Final result

`G:\onecreations\runs\d2_run1\deliverables\final.mp4` (768×448, 49 frames, 24 fps; SHA-256 `5c3c8361…f08c`; the QC'd
lossless master `grade/final_master.mp4` `b5a58e2c…1d8c`). Final QC 5/5 pass: final valid; protected weapon present
in all 49 frames (min NCC 0.81); effects first change at f29 with 0 change before; bounded repair 0.0; no holes.

## 22. Autonomy audit — **PASS**

- One invocation (21:43:40 → 21:52:14 IST, exit 0); no `--resume`, no code or configuration change during the run.
- No manual Blender, ComfyUI, compositor, frame or file action; every stage was run by the executor (console log
  and `execution.json`).
- Before invocation (allowed, recorded): the rehearsal (§ below), the pre-registration commit, and the owner closing
  Chrome on request (RAM rule). Nothing was touched after the command started.

Rehearsal (not a result): the same prompt ran all stages except LTX with Showcase run 1's raw video as a stand-in
(`rehearsal_d2_1`, 468 s, all QC pass; weapon failure detected at f25–27). It proved the deterministic stages on real
data before the one generation was spent; it found no bugs.

## 23. Control result — **PASS**

Framing ≤ 2.8 px, contact on the authored frame (0 frames), apex present, camera progression coherent (≤ 4 px), actor
placement unchanged, critical weapon geometry protected (policy repair + final presence). Visual (owner-independent,
by me from the contact sheets): the strike reads guard → wind-up → apex → strike → contact → recovery, and the arm
articulates through every phase.

## 24. Pipeline result — **PASS**

All 15 stages `done` in order, each with key, times and hashed outputs; effects derived from CONTACT (Blender frames
30–49); REPAIR ran because the compiled policy says so; the run status was set by QC (post-generation decision
`proceed`, final QC passed) with no manual verdict.

## 25. Final integrity result — **PASS**

Valid 768×448×49 video, protected mace readable, impact effects synchronised with contact, no holes and no major
compositing corruption. One visible artefact, by design and as in Showcase v1: at f26 the 90°-shutter motion blur of
the Blender mace (~76 px/frame) reads as an orange streak.

## 26. Appearance result — **IMPROVED** (attacker); environment, defender, look: Showcase-comparable

Against the Showcase v1 final at f4/f23/f29/f40: asura_v2's breastplate, separated abdominals, knee guards, plate
rims, larger head and wrapped grip persist through generation f0–f48, and the torso no longer reads as one fused
crimson mass. It is still clearly stylised CG (metaball forms, rigid fingers, plain cloth panels). The temple, the
defender, the dusk look and the effects are as in Showcase v1.

## 27. Performance and resources (measured)

| Stage | s | | Stage | s |
|---|---|---|---|---|
| PLAN + VALIDATE + COMPILE | 0.06 | | POST_GENERATION_QC | 5.7 |
| BLENDER_BUILD | 3.9 | | REPAIR | 104.8 |
| CONTROL_RENDER (export, depth, 2 references) | 240.3 | | VFX | 65.6 |
| FIRST_FRAME (1024 spp) | 18.3 | | COMPOSITE | 6.3 |
| PREFLIGHT_QC | 7.6 | | GRADE | 1.3 |
| LTX_GENERATE | 49.3 | | FINAL_QC | 10.7 |
| | | | DELIVER | 0.4 |

Total wall 514.2 s. LTX telemetry (monitor, 1 s samples): peak VRAM 11,501 MB; peak RAM used 30,461 MB; minimum free
RAM 2,048 MB; peak commit 46,772 of 60,157 MB (77.7 %); pagefile 142 → 176 MB (+34 MB); PCIe gen4 x16 under load
with one gen2 x16 sample (weight streaming, as before; idle gen1). Storage G: 236.52 → 236.09 GiB for the run
(442 MB). Blender stages dominate (≈ 85 % of wall time); LTX is ≈ 10 %.

## 28. Limitations

- The supported domain is one shot class: this temple, this attacker (v1/v2), this defender, one mace slam, one guard,
  one orbit+push camera family, one look, these four impact effects. Anything else is refused at PLAN/VALIDATE.
- Post-generation QC is template matching against the Blender reference; it detects gross framing, timing, camera
  and weapon failures, not subtle anatomy or identity drift, and it does not judge cinematic quality.
- The weapon is repaired by replacement in every run (policy); raw LTX still cannot render the fast mace.
- Planner defaults are not yet listed as DirectorPlan decisions (§17).
- The defender is static and its trident is not separately maskable; no parry contact.
- asura_v2's admission metrics are proxies chosen with the comparison; its fingers are rigid.
- One run, one seed: this demonstrates the pipeline, not a distribution of outcomes.

## 29. Conservative capability claim

For a request inside the registered Showcase class, one local command on the RTX 4070 / 32 GB desktop now produces a
graded 768×448, 49-frame (≈ 2 s) shot end to end in about 8.5 minutes, with every decision traceable to the prompt,
a registry default or a rule, every stage hashed and resumable, and automatic measurable QC deciding the run state;
demonstrated once (d2_run1). It is not general text-to-video.

## 30. Next milestone (proposed, not started)

**D3 (proposed):** widen the supported domain by one axis at a time without new models. Candidates: (a) a reactive
defender (rigged block/parry with contact), the V1 "one readable parry"; (b) a second camera family and shot length
via windowing; (c) record planner defaults as decisions and add a stage-level time budget (CONTROL_RENDER and REPAIR
are 67 % of wall time). Owner to choose.
