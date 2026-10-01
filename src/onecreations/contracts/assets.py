"""Project index and asset contracts (v1 §7, §9)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from onecreations.contracts.common import FileRef, FrameRateModel, Id, Matrix4, Model, RightsRecord

AssetKind = Literal["character", "prop", "weapon", "environment", "fx_preset", "audio", "reference"]


class AssetRef(Model):
    id: Id
    kind: AssetKind
    version: str
    manifest: str | None = None  # relative path to e.g. a CharacterAsset manifest
    rights: RightsRecord | None = None


class Project(Model):
    """Top-level project index. Paths are relative to the project directory."""
    schema_version: Literal[1] = 1
    id: Id
    title: str
    units: Literal["meters"] = "meters"
    coordinate_system: Literal["blender_z_up"] = "blender_z_up"
    default_fps: FrameRateModel
    assets: list[AssetRef] = []
    camera_motions: list[str] = []
    choreographies: list[str] = []
    timewarps: list[str] = []
    events: list[str] = []
    backend_profiles: list[str] = []
    shots: list[str] = []
    scene_states: list[Id] = []
    lighting: list[Id] = []
    references: list[Id] = []
    mask_layers: list[Id] = Field(default=[], description="Region names usable in allowed/protected regions")

    @model_validator(mode="after")
    def _unique_assets(self) -> "Project":
        ids = [a.id for a in self.assets]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate asset ids: {dupes}")
        return self


class WeaponSocket(Model):
    name: Id
    bone: str
    transform: Matrix4 = Field(description="Socket transform in bone space, row-major 4x4, meters")


class SymbolSpec(Model):
    """Design-critical symbol whose orientation must never mirror (v1 §9)."""
    name: Id
    description: str
    location: str
    mirror_allowed: bool = False


class StateVariant(Model):
    id: Id
    description: str
    changes: list[str]


class SkeletonSpec(Model):
    rig_id: str
    bone_map: dict[str, str] = Field(description="canonical joint name → rig bone name")


class CharacterAsset(Model):
    """Design authority for a persistent character (v1 §9)."""
    schema_version: Literal[1] = 1
    id: Id
    version: str
    display_name: str
    units: Literal["meters"] = "meters"
    height_m: float = Field(gt=0)
    measurements_m: dict[str, float] = {}
    handedness: Literal["right", "left", "ambidextrous"]
    skeleton: SkeletonSpec
    weapon_sockets: list[WeaponSocket] = []
    material_ids: dict[str, int] = {}
    symbols: list[SymbolSpec] = []
    detail_inventory: list[str] = []
    expressions: list[str] = []
    allowed_variations: list[str] = []
    state_variants: list[StateVariant] = []
    files: list[FileRef] = []
    rights: RightsRecord

    @model_validator(mode="after")
    def _checks(self) -> "CharacterAsset":
        for label, names in (("weapon socket", [s.name for s in self.weapon_sockets]),
                             ("state variant", [v.id for v in self.state_variants]),
                             ("symbol", [s.name for s in self.symbols])):
            dupes = sorted({n for n in names if names.count(n) > 1})
            if dupes:
                raise ValueError(f"duplicate {label} names: {dupes}")
        bones = set(self.skeleton.bone_map.values())
        missing = [s.name for s in self.weapon_sockets if s.bone not in bones]
        if missing:
            raise ValueError(f"weapon sockets reference bones not in skeleton.bone_map: {missing}")
        ids = list(self.material_ids.values())
        if len(ids) != len(set(ids)):
            raise ValueError("material_ids values must be unique")
        return self
