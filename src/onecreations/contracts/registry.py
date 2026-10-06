"""Asset registry contract (D1): the small library of assets, actions, cameras, effects, looks, grades, generation
profiles and protection rules the director may choose from. Only things that actually exist are registered.

Every entry says what it is, how the engine builds it (`builder`), where its evidence comes from (`provenance`), what
it can be configured with (`params`) and what it cannot do (`limitations`). Kind-specific metadata lives in `data`
and is checked for its required keys, so a malformed library fails at load time, not inside Blender.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from onecreations.contracts.common import Id, Model

AssetKind = Literal["character", "weapon", "environment", "action", "camera", "vfx", "look", "grade",
                    "generation_profile", "protection_rule"]

REQUIRED_DATA = {
    "character": {"oc_id", "pass_index", "semantic_name", "motion", "anchors", "prompt", "default_placement"},
    "weapon": {"parts", "weapon_class", "mount", "prompt"},
    "environment": {"semantic_objects", "prompt"},
    "action": {"actor_motion", "frames", "fps", "events", "phases"},
    "camera": {"family", "defaults", "envelope"},
    "vfx": {"component", "layer", "trigger_event"},
    "look": {"lighting", "sun", "prompt"},
    "grade": {"finish"},
    "generation_profile": {"backend", "workflow", "resolution", "frames", "fps", "steps", "nodes", "prompt_template"},
    "protection_rule": {"layer_settings", "applies_to_weapon_class"},
}


class ParamSpec(Model):
    type: Literal["number", "integer", "vec3", "string", "bool", "choice"]
    default: Any = None
    min: float | None = None
    max: float | None = None
    choices: list[str] = []
    description: str = ""

    def check(self, name: str, value: Any) -> str | None:
        """None if `value` is acceptable, else a message."""
        if self.type in ("number", "integer"):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return f"{name} must be a number"
            if self.type == "integer" and int(value) != value:
                return f"{name} must be an integer"
            if self.min is not None and value < self.min or self.max is not None and value > self.max:
                return f"{name}={value} outside [{self.min}, {self.max}]"
        if self.type == "choice" and value not in self.choices:
            return f"{name}={value!r} not one of {self.choices}"
        if self.type == "vec3" and (not isinstance(value, (list, tuple)) or len(value) != 3):
            return f"{name} must be [x, y, z]"
        return None


class AssetEntry(Model):
    id: Id
    kind: AssetKind
    status: Literal["proven", "experimental"] = "proven"
    description: str
    aliases: list[str] = Field(default=[], description="lower-case words/phrases the prompt interpreter maps here")
    builder: str = Field(description="how the current engine builds it (file:function or pipeline stage)")
    provenance: str = Field(description="where the evidence for this entry comes from")
    limitations: list[str] = []
    params: dict[str, ParamSpec] = {}
    data: dict[str, Any] = {}

    @model_validator(mode="after")
    def _data_keys(self) -> "AssetEntry":
        missing = REQUIRED_DATA[self.kind] - set(self.data)
        if missing:
            raise ValueError(f"{self.kind} {self.id}: data is missing {sorted(missing)}")
        return self


class AssetRegistry(Model):
    schema_version: Literal[1] = 1
    id: Id
    engine: Id = Field(description="the scene engine these entries are built by")
    entries: list[AssetEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> "AssetRegistry":
        ids = [e.id for e in self.entries]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate registry ids: {dupes}")
        return self
