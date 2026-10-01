"""Load a project directory (project.json + referenced manifests) into a ShotContext for validation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from onecreations.camera.io_csv import read_csv
from onecreations.camera.trajectory import CameraTrajectory
from onecreations.contracts import (ActionTimeline, AssetRef, CameraMotion, ModelBackend, Project, Shot, TimeWarpModel,
                                    VFXEvent)
from onecreations.shotpkg.issues import Issue


def read_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        return yaml.safe_load(text)
    return json.loads(text)


def load_trajectory(path: Path) -> CameraTrajectory:
    if path.suffix.lower() == ".csv":
        return read_csv(path)
    return CameraTrajectory.load_npz(path)


@dataclass
class ShotContext:
    root: Path | None = None
    project: Project | None = None
    assets: dict[str, AssetRef] = field(default_factory=dict)
    camera_motions: dict[str, CameraMotion] = field(default_factory=dict)
    camera_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    choreographies: dict[str, ActionTimeline] = field(default_factory=dict)
    timewarps: dict[str, TimeWarpModel] = field(default_factory=dict)
    events: dict[str, VFXEvent] = field(default_factory=dict)
    backends: dict[str, ModelBackend] = field(default_factory=dict)
    scene_states: set[str] = field(default_factory=set)
    lighting: set[str] = field(default_factory=set)
    references: set[str] = field(default_factory=set)
    mask_layers: set[str] = field(default_factory=set)


def _load_many(root: Path, rels: list[str], model, issues: list[Issue], code: str) -> list[tuple[Path, Any]]:
    out = []
    for rel in rels:
        path = root / rel
        try:
            out.append((path, model.model_validate(read_document(path))))
        except FileNotFoundError:
            issues.append(Issue(code, "error", f"file not found: {rel}", rel))
        except (ValidationError, ValueError) as exc:
            issues.append(Issue(code, "error", f"{rel}: {exc}", rel))
    return out


def load_project(project_dir: str | Path) -> tuple[ShotContext, dict[str, Shot], list[Issue]]:
    """Load everything a project lists. Problems become issues instead of exceptions where possible."""
    root = Path(project_dir)
    issues: list[Issue] = []
    project = Project.model_validate(read_document(root / "project.json"))
    ctx = ShotContext(root=root, project=project,
                      assets={a.id: a for a in project.assets},
                      scene_states=set(project.scene_states), lighting=set(project.lighting),
                      references=set(project.references), mask_layers=set(project.mask_layers))

    for path, cam in _load_many(root, project.camera_motions, CameraMotion, issues, "LOAD_CAMERA"):
        ctx.camera_motions[cam.id] = cam
        traj_path = path.parent / cam.trajectory
        try:
            traj = load_trajectory(traj_path)
            ctx.camera_ranges[cam.id] = (traj.start, traj.end)
        except (OSError, ValueError, KeyError) as exc:
            issues.append(Issue("LOAD_CAMERA_SAMPLES", "error", f"{cam.id}: cannot load {cam.trajectory}: {exc}", cam.id))
    for _, item in _load_many(root, project.choreographies, ActionTimeline, issues, "LOAD_CHOREOGRAPHY"):
        ctx.choreographies[item.id] = item
    for _, item in _load_many(root, project.timewarps, TimeWarpModel, issues, "LOAD_TIMEWARP"):
        ctx.timewarps[item.id] = item
    for _, item in _load_many(root, project.events, VFXEvent, issues, "LOAD_EVENT"):
        ctx.events[item.id] = item
    for _, item in _load_many(root, project.backend_profiles, ModelBackend, issues, "LOAD_BACKEND"):
        ctx.backends[item.id] = item
    shots = {s.id: s for _, s in _load_many(root, project.shots, Shot, issues, "LOAD_SHOT")}
    return ctx, shots, issues
