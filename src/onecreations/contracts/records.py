"""Experiment cards and admission records (v1 §29, runbooks M3/M6)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

from onecreations.contracts.common import Model


class ExperimentRecord(Model):
    """Matches `training/**/experiment-card*.yaml`. Free-form sections stay dicts until the trainer is pinned."""
    id: str
    status: Literal["proposed", "ready", "running", "done", "rejected"]
    hypothesis: str
    purpose: str | None = None
    baseline_failure: str
    base_model: str
    deployment_model: str | None = None
    init_adapter: str | None = None
    data: dict[str, Any]
    method: dict[str, Any]
    compute: dict[str, Any]
    evaluation: dict[str, Any]
    stop_rules: list[str] = []
    results: dict[str, Any] = {}
    decision: str | None = None


class AdmissionSummary(Model):
    model_config = ConfigDict(extra="allow")
    peak_gpu_mem_used_mb: float | None = None
    peak_ram_used_mb: float | None = None
    min_ram_available_mb: float | None = None
    peak_swap_used_mb: float | None = None
    peak_proc_tree_rss_mb: float | None = None
    baseline_gpu_mem_used_mb: float | None = None
    baseline_swap_used_mb: float | None = None
    swap_growth_mb: float | None = None
    samples: int
    auto_flags: list[str] = []


class AdmissionRecord(Model):
    """One line of `admission_records/records.jsonl` written by tools/admission/monitor.py."""
    label: str
    started_at: str
    wall_seconds: float
    mode: Literal["command", "attach"]
    command: list[str]
    exit_code: int | None
    interrupted: bool
    notes: str = ""
    settings: dict[str, str] = {}
    host: dict[str, Any]
    summary: AdmissionSummary
    samples_csv: str | None
    outcome: str | None = Field(default=None, pattern=r"^(pass|partial|fail)\b")
    provenance: Literal["measured"]
