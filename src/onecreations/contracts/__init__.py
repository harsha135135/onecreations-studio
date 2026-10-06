"""Pydantic v2 contracts. Each contract has a JSON Schema in `schemas/` (regenerate with `onecreations schemas export`)."""

from onecreations.contracts.action import ActionTimeline, ContactInterval, Phase, TimeWarpModel
from onecreations.contracts.assets import AssetRef, CharacterAsset, Project
from onecreations.contracts.backend import FrameCountRule, ModelBackend
from onecreations.contracts.camera import CameraIntrinsicsModel, CameraMotion
from onecreations.contracts.composite import CompositeLayer, CompositeManifest
from onecreations.contracts.director import CompiledShot, DirectorPlan, ShotSpec
from onecreations.contracts.registry import AssetRegistry
from onecreations.contracts.export import ExportManifest
from onecreations.contracts.records import AdmissionRecord, ExperimentRecord
from onecreations.contracts.shot import GenerationSpec, Shot
from onecreations.contracts.vfx import VFXEvent

CONTRACTS = {
    "project": Project,
    "character_asset": CharacterAsset,
    "camera_motion": CameraMotion,
    "action_timeline": ActionTimeline,
    "timewarp": TimeWarpModel,
    "vfx_event": VFXEvent,
    "shot": Shot,
    "model_backend": ModelBackend,
    "experiment_record": ExperimentRecord,
    "admission_record": AdmissionRecord,
    "export_manifest": ExportManifest,
    "composite_manifest": CompositeManifest,
    "shot_spec": ShotSpec,
    "director_plan": DirectorPlan,
    "compiled_shot": CompiledShot,
    "asset_registry": AssetRegistry,
}

__all__ = [
    "CONTRACTS", "ActionTimeline", "AdmissionRecord", "AssetRef", "AssetRegistry", "CompiledShot", "DirectorPlan",
    "ShotSpec", "CameraIntrinsicsModel", "CameraMotion",
    "CharacterAsset", "CompositeLayer", "CompositeManifest", "ContactInterval", "ExperimentRecord", "ExportManifest",
    "FrameCountRule", "GenerationSpec", "ModelBackend", "Phase", "Project", "Shot", "TimeWarpModel", "VFXEvent",
]
