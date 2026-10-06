"""Blender → OneCreations export bundle contract (written by integrations/blender/oc_export.py).

A bundle directory holds `export_manifest.json` plus NPZ arrays. Arrays are verified by content digest
(`hashing.array_digest`), not file bytes, because NPZ files embed zip timestamps.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from onecreations.contracts.camera import CameraIntrinsicsModel
from onecreations.contracts.common import FrameRateModel, Id, Model, RationalTime, Sha256


class ArrayFile(Model):
    file: str
    digest: Sha256
    keys: list[str]


class ExportScene(Model):
    name: str
    fps: FrameRateModel
    frame_start: int
    frame_end: int
    length_unit: str
    unit_scale: float


class ExportShot(Model):
    id: str
    output_fps: FrameRateModel
    frame_count: int = Field(gt=0)
    duration: RationalTime
    timewarp_keys: list[tuple[RationalTime, RationalTime]]


class ExportFrame(Model):
    index: int = Field(ge=0)
    output_time: RationalTime
    source_time: RationalTime
    blender_frame: RationalTime = Field(description="Exact Blender frame number (frame_start + source_time × fps)")


class ExportCamera(Model):
    object_name: str
    intrinsics: CameraIntrinsicsModel
    samples: ArrayFile
    animated_lens: bool
    animated_shift: bool


class ExportObject(Model):
    oc_id: Id
    name: str
    type: str
    pass_index: int
    bound_box_local: list[list[float]] = Field(description="8 local-space corners (Blender order)")


class ExportArmature(Model):
    oc_id: Id
    name: str
    bones: list[str]


class DepthCheck(Model):
    measured_convention: Literal["planar", "euclidean", "unverified"]
    probes: int
    median_error_planar_m: float | None
    median_error_euclidean_m: float | None
    stored_as: Literal["planar", "raw"]


class ExportPasses(Model):
    engine: str
    samples: int
    filter_width: float
    width: int
    height: int
    file: ArrayFile
    background_depth: Literal["inf"] = "inf"
    depth: DepthCheck
    normal_space: Literal["world"] = "world"
    object_index_map: dict[str, int]
    excluded_volume_objects: list[str] = Field(
        default=[], description="volume-only helpers (e.g. a haze box) hidden while rendering the geometric passes; "
                                "written only when non-empty")
    material_index_map: dict[str, int] = Field(
        default={}, description="material name -> material pass index (--material-index): per-part masks; "
                                "written only when the pass is exported")
    excluded_objects: list[str] = Field(
        default=[], description="objects flagged oc_exclude_from_passes (e.g. semi-transparent flames) hidden while "
                                "rendering the geometric passes; written only when non-empty")


class ExportManifest(Model):
    schema_version: Literal[1] = 1
    exporter_version: str
    blender_version: str
    source_file: str
    conventions: dict[str, str]
    scene: ExportScene
    shot: ExportShot
    frames: list[ExportFrame]
    camera: ExportCamera
    objects: list[ExportObject] = []
    objects_file: ArrayFile | None = None
    armatures: list[ExportArmature] = []
    joints_file: ArrayFile | None = None
    probe_labels: list[str] = []
    probes_file: ArrayFile | None = None
    passes: ExportPasses | None = None
    deferred: list[str] = []
    content_sha256: Sha256
