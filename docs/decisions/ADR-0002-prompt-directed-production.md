# ADR-0002 — Prompt-directed production with Blender as an internal deterministic scene engine

- **Status:** accepted (owner direction, 2026-10-06); first implementation is milestone D1.
- **Supersedes:** nothing. ADR-0001 (hardware and compute) still holds.
- **Placement:** this ADR lives in `docs/decisions/`, beside ADR-0001, so there is one decision folder.

## Context

R2D → M2-A/B/C → M3-A → Showcase v1 proved one pipeline end to end on the RTX 4070 / 32 GB:

Blender authored control → depth + first frame → LTX-2.5 Union → deterministic repair → effects → grade.

Every one of those shots was configured by hand, though: constants in Python builders, command lines, hard-coded
frame numbers. The product the owner wants is **prompt → final video**: the user describes the shot and presses
GENERATE. Blender must stay deeply involved but become an implementation detail.

## Decision

### 1. Final UX: prompt → video

The user never builds a Blender scene for a supported shot class. Blender, the controls, the compositor and the
generative backend are internal stages.

### 2. Structured 3D control is retained

The project's evidence is that authored geometry, timing and camera are what make the output controllable:
- timing to the frame (M2-B)
- coherent camera parallax (M2-C)
- control kept under a finished look (M3-A)
- a protected weapon (Showcase)

A prompt therefore becomes a **3D production plan**, not a text-to-video call.

### 3. Four separated layers, never collapsed

| Layer | Holds | Contract |
|---|---|---|
| Request | what the user wants (natural language) | a string |
| DirectorPlan | what the director decided, with the evidence for each decision (prompt match, default, rule), warnings and unsupported requests | `contracts/director.py:DirectorPlan` |
| ShotSpec | what the shot requires: semantic entities (ASURA, MACE, TEMPLE, GROUND …), registry assets, action/camera/look/grade presets, events as `action.EVENT` references, protection overrides, QC profile; no engine details, no code | `ShotSpec` |
| CompiledShot | how the current engine executes it: resolved frames, ActionTimeline, camera move, the Blender builder config, CompositeManifest, LTX job (workflow + overrides + composed prompt), grade, semantic-object/mask/policy map, QC checks, stage list | `CompiledShot` |

The v1 `Shot` contract remains the project-file reference package; `ShotSpec` is the director's engine-independent
intent.

### 4. Asset registry

`library/registry.yaml` (validated by `contracts/registry.py`) lists only real, built assets:
- characters, weapons, environments
- actions, camera presets, effects
- looks, grades
- generation profiles, protection rules

Each entry records:
- how it is built
- its provenance (which run proved it)
- its parameters
- its required anchors and compatibility (rig, weapon class)
- its known limitations

### 5. Semantic identities

The director and the spec think in semantic identities (ASURA, SHIVA, MACE, TEMPLE, GROUND, SHRINE). The compiler
maps them to engine objects (`sc_asura`, pass index 1 …). The user never sees an engine object name.

### 6. Action presets own their timing and expose semantic events

Action presets expose START / GUARD_END / APEX / CONTACT / HOLD_END / RECOVERY_START / END. Some events move with
parameters: CONTACT = APEX + strike_frames.

Effects, the grade jolt, compositor triggers and QC refer to `strike.CONTACT`, never to a frame. Change the timing
and every dependent effect moves. Frame numbers exist only in the CompiledShot.

### 7. Camera presets carry safe defaults and an admitted envelope

`orbit_push_v1` has low and high variants. Its envelope comes from M2-C, M3-A and the Showcase:
- orbit ≤ 24°
- push-in ≤ 1.5 m
- height 1.9–3.6 m
- lens 32–35 mm, fixed
- no roll

Requests outside the envelope are rejected, not silently clamped.

### 8. Processing policies are composable and rule-selected

A policy decides independently:
- appearance: generative or deterministic
- geometry: generative or protected (Blender owns it)
- timing: always authored
- editability: allowed only if the mask is separable

Rules are deterministic engineering heuristics with recorded provenance. For example, P1 protects a heavy weapon
whose estimated peak speed is ≥ 0.7 head widths/frame. That is a local M2-B observation, not a universal LTX
limit. An explicit spec override wins.

### 9. Masking architecture

Every renderable is a SemanticObject that records:
- its engine ids
- its pass indices (the MaskProvider today is the object-index pass)
- mask separability
- depth source
- material groups
- policy
- protected layer

This keeps "make the Asura's armour black" possible later: it needs per-material masks (Cryptomatte or a material
index pass) and a masked-edit backend, neither of which exists yet. Nothing in the spec prevents them.

*D2 clarification (2026-10-06):* the material-index pass now exists (`oc_export --material-index`, Cycles IndexMA)
and a character entry may declare `material_masks` (part → material pass index; `asura_v2`: skin, armour,
cloth_harness, head_details). A per-part mask is the object mask AND the material index. The masked-edit backend
still does not exist.

### 10. QC is data

QC checks are declared per stage (`preflight` / `post_generation` / `final`) with an `implemented` flag. D1
evaluates the preflight checks; post-generation checks are declared so automatic QC can plug in later.

*D2 clarification (2026-10-06):* the post-generation and final checks are implemented (`director/video_qc.py`).
Each post-generation check declares its failure action (`on_fail`: `repair`, `regenerate` or `fail`). A repair is
never triggered by QC alone: the compiled ProcessingPolicy (geometry `protected`) schedules it, and QC's weapon
evidence is recorded with it. Only `regenerate` checks may cause a second generation, once, with the same seed.

### 11. The director is replaceable

D1's interpreter (`keyword_v1`) matches registry aliases deterministically and refuses what the library lacks. An
LLM director later only has to produce the same `DirectorPlan`. Everything downstream is unchanged. No paid API and
no downloaded model are required.

### 12. The video backend is replaceable

The generation stage is a `generation_profile` registry entry: workflow, node overrides, resolution, frames, steps
and a prompt template. A different backend is a new profile plus its stage implementation; ShotSpecs do not change.

### 13. Honest scope

The supported shot class is exactly what the registry holds. Arbitrary characters, environments and actions are
refused with a reason. Text-to-3D, asset retrieval, procedural synthesis, motion generation and retargeting are
future milestones that add registry entries and builders. They do not change these layers.

## Consequences

- New visual work, including M3-B's character upgrade, is done as reusable registry assets and presets the director
  can select, not as one-off scenes.
- Engine builders take a compiled configuration (`build_showcase_scene.py --config`). With no configuration they
  keep their proven defaults, so past results stay reproducible.
- A capability is claimed only for the stages actually orchestrated. In D1 that is prompt → validated spec →
  compiled configuration → Blender scene, controls, first frame, masks and preflight QC. LTX, repair, compositing
  and grade exist as proven stages but are not orchestrated yet.

## D3 clarification (2026-10-07)

- **Contacts between actors (§6):** an action may declare a weapon-on-weapon `contact` with a `partner_action`; the
  partner syncs its timing parameters, validation requires one shared CONTACT frame (`SPEC_SYNC_CONTACT`), and the
  CompiledShot's ActionTimeline carries the contact interval. The engine solves the attacker's contact pose against
  the defender's authored block, so the contact holds by construction.
- **Variants chosen by capability:** when the requested action needs a rig the named character lacks, the director
  picks the registered rigged variant of the same character (ascetic_defender_v1 → v2) and records why.
- **P6 (§8):** a weapon that takes part in an authored contact gets protected geometry (`contact_weapon_v1`); P1 is
  checked first.
- **QC (§10):** checks for a contact are declared only for shots with a contact, so earlier compiled shots are
  unchanged; a declared check with no evaluator now raises.
- **Open (D3 doc §16):** `contact_timing` measures the raw weapon head. For a mid-air contact whose weapons are both
  policy-protected, d3_run1 shows it failing while the generated hand is on time; changing it needs a new
  pre-registered run.
