"""Prompt-directed production contracts (D1). Four separate layers, never collapsed into one object:

    natural-language request  (what the user wants: a string)
    DirectorPlan              (what the director decided, with the evidence for each decision)
    ShotSpec                  (what the shot requires: semantic entities, presets, events; no engine details)
    CompiledShot              (how the current engine executes it: resolved frames, scene build, layers, workflow)

ShotSpec refers to SEMANTIC identities (ASURA, MACE, TEMPLE ...) and registry ids; it never names Blender objects or
contains code. Timing dependencies are semantic events (`strike.CONTACT`), resolved to frames only by the compiler, so
moving the contact moves every dependent effect. The v1 `Shot` contract (shot.py) remains the project-file reference
package; ShotSpec is the engine-independent intent a director produces.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from onecreations.contracts.action import ActionTimeline
from onecreations.contracts.common import Id, Model, RationalTime, Sha256, Vec3
from onecreations.contracts.composite import CompositeManifest

SemanticId = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=64)]
"""A semantic identity the director thinks in: ASURA, DEFENDER, MACE, TEMPLE, GROUND, SHRINE."""

EventName = Literal["START", "GUARD_END", "APEX", "CONTACT", "HOLD_END", "RECOVERY_START", "END"]


# --- DirectorPlan ------------------------------------------------------------------------------------------------

class Decision(Model):
    slot: str = Field(description="e.g. environment, attacker, attacker.action, camera.variant, vfx")
    choice: str
    source: Literal["prompt", "default", "rule"]
    evidence: str | None = Field(default=None, description="the matched prompt text, or the rule id")
    note: str | None = None


class DirectorPlan(Model):
    schema_version: Literal[1] = 1
    request: str
    interpreter: str = Field(description="which planner produced this (e.g. keyword_v1); replaceable by an LLM")
    supported: bool
    environment: Id | None = None
    characters: dict[str, Id] = Field(default={}, description="role -> character asset")
    semantic_names: dict[str, SemanticId] = Field(default={}, description="role -> semantic identity")
    weapons: dict[str, Id] = Field(default={}, description="owner role -> weapon asset")
    actions: dict[str, Id] = Field(default={}, description="role -> action preset")
    action_params: dict[str, dict[str, float | int]] = {}
    camera: Id | None = None
    camera_variant: str | None = None
    look: Id | None = None
    vfx: list[Id] = []
    predicted_protection: dict[str, Id] = Field(default={}, description="semantic object -> protection rule "
                                                                       "(the compiler's rules, previewed)")
    decisions: list[Decision] = []
    warnings: list[str] = []
    unsupported: list[str] = Field(default=[], description="requested things the current library cannot do")


# --- ShotSpec ----------------------------------------------------------------------------------------------------

class Placement(Model):
    position: Vec3
    yaw_deg: float = 0.0
    scale: float = Field(default=1.0, gt=0)


class EnvironmentSpec(Model):
    id: SemanticId = "TEMPLE"
    asset: Id


class CharacterSpec(Model):
    id: SemanticId
    role: Literal["attacker", "defender", "bystander"]
    asset: Id
    placement: Placement | None = Field(default=None, description="None: the asset's default staging")
    appearance: Id = "default"


class PropSpec(Model):
    id: SemanticId
    asset: Id
    owner: SemanticId
    mount: Literal["weapon_hand", "integrated"] = "weapon_hand"


class ActionSpec(Model):
    id: Id = Field(description="action instance id, used by event references (e.g. strike)")
    actor: SemanticId
    preset: Id
    params: dict[str, float | int] = {}
    target: SemanticId | None = None


class EventRef(Model):
    action: Id
    event: EventName
    offset_frames: int = 0


class EffectEventSpec(Model):
    id: Id
    preset: Id = Field(description="vfx registry id")
    trigger: EventRef
    params: dict[str, Any] = {}


class TargetRef(Model):
    anchor: SemanticId
    offset: Vec3 = (0.0, 0.0, 0.0)


class CameraSpec(Model):
    preset: Id
    variant: str | None = None
    target: TargetRef
    params: dict[str, Any] = Field(default={}, description="overrides of the preset (validated against its envelope)")


class LookSpec(Model):
    preset: Id
    params: dict[str, Any] = {}


class GenerationSettings(Model):
    profile: Id
    seed: int = 1000
    style: str | None = Field(default=None, description="optional extra appearance words appended to the prompt")


class ProtectionSpec(Model):
    object: SemanticId
    rule: Id | Literal["none"] = Field(description="protection rule id, or none to trust the generated output")


class GradeSpec(Model):
    preset: Id
    params: dict[str, Any] = {}


class ShotSpec(Model):
    schema_version: Literal[1] = 1
    id: Id
    description: str = ""
    duration_frames: int = Field(gt=0)
    fps: int = Field(default=24, gt=0)
    resolution: tuple[int, int]
    environment: EnvironmentSpec
    characters: list[CharacterSpec] = Field(min_length=1)
    props: list[PropSpec] = []
    actions: list[ActionSpec] = []
    camera: CameraSpec
    look: LookSpec
    events: list[EffectEventSpec] = []
    generation: GenerationSettings
    protection: list[ProtectionSpec] = Field(default=[], description="explicit overrides; otherwise the compiler's "
                                                                     "policy rules decide")
    compositing: Id = "protected_layers_v1"
    grade: GradeSpec
    qc_profile: Id = "showcase_class_preflight_v1"

    @model_validator(mode="after")
    def _unique_ids(self) -> "ShotSpec":
        sem = [self.environment.id] + [c.id for c in self.characters] + [p.id for p in self.props]
        for label, items in (("semantic", sem), ("action", [a.id for a in self.actions]),
                             ("event", [e.id for e in self.events])):
            dupes = sorted({i for i in items if items.count(i) > 1})
            if dupes:
                raise ValueError(f"duplicate {label} ids: {dupes}")
        return self


# --- CompiledShot ------------------------------------------------------------------------------------------------

class ProcessingPolicy(Model):
    """How the pipeline treats one semantic object. Composable: appearance and geometry are decided separately."""
    appearance: Literal["generative", "deterministic"] = "generative"
    geometry: Literal["generative", "protected"] = "generative"
    timing: Literal["authored"] = "authored"
    editable: bool = Field(default=False, description="a future masked edit may target it (mask must be separable)")
    rule: Id | None = None
    provenance: str = ""


class SemanticObject(Model):
    id: SemanticId
    kind: Literal["character", "weapon", "environment_part", "effect"]
    asset: Id
    oc_ids: list[str]
    pass_indices: list[int] = []
    mask_source: Literal["object_index_pass", "effect_layer_alpha", "none"] = "object_index_pass"
    mask_separable: bool = Field(description="False when it shares pass indices with another object")
    depth: Literal["depth_pass", "none"] = "depth_pass"
    material_groups: list[str] = Field(default=[], description="finer edit regions (future: per-material masks)")
    policy: ProcessingPolicy
    protected_layer: Id | None = None


class ResolvedEvent(Model):
    name: str = Field(description="action.EVENT, e.g. strike.CONTACT")
    frame: int = Field(ge=0)
    time: RationalTime


class QCCheck(Model):
    id: Id
    stage: Literal["preflight", "post_generation", "final"]
    kind: str
    params: dict[str, Any] = {}
    implemented: bool
    provenance: str = ""


class Stage(Model):
    id: Id
    implemented: bool
    in_dry_run: bool = False
    notes: str = ""


class GenerationJob(Model):
    backend: str
    workflow: str
    workflow_sha256: Sha256
    overrides: dict[str, dict[str, Any]] = Field(description="node id -> input -> value")
    prompt: str
    seed: int
    steps: int
    resolution: tuple[int, int]
    frames: int


class CompiledShot(Model):
    schema_version: Literal[1] = 1
    shot_id: Id
    compiler: str
    spec_sha256: Sha256
    registry_sha256: Sha256
    engine: Id
    frames: int
    fps: int
    resolution: tuple[int, int]
    events: list[ResolvedEvent]
    action_timeline: ActionTimeline
    camera_move: dict[str, Any]
    scene_build: dict[str, Any] = Field(description="the engine builder's configuration (JSON, no code)")
    layers: CompositeManifest
    generation: GenerationJob
    grade: dict[str, Any]
    semantic_objects: list[SemanticObject]
    qc: list[QCCheck]
    stages: list[Stage]
    notes: list[str] = []
