"""Asset registry access: load and validate library/registry.yaml, look entries up by id and kind, match aliases."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from onecreations.blender_bridge import REPO_ROOT
from onecreations.contracts.registry import AssetEntry, AssetRegistry
from onecreations.hashing import content_hash

DEFAULT_REGISTRY = REPO_ROOT / "library" / "registry.yaml"


class RegistryError(KeyError):
    pass


class Registry:
    def __init__(self, model: AssetRegistry):
        self.model = model
        self._by_id = {e.id: e for e in model.entries}

    @property
    def engine(self) -> str:
        return self.model.engine

    @property
    def sha256(self) -> str:
        return content_hash(self.model.model_dump(mode="json"))

    def has(self, asset_id: str, kind: str | None = None) -> bool:
        e = self._by_id.get(asset_id)
        return e is not None and (kind is None or e.kind == kind)

    def get(self, asset_id: str, kind: str | None = None) -> AssetEntry:
        e = self._by_id.get(asset_id)
        if e is None:
            raise RegistryError(f"no registry entry {asset_id!r}")
        if kind is not None and e.kind != kind:
            raise RegistryError(f"{asset_id!r} is a {e.kind}, not a {kind}")
        return e

    def of_kind(self, kind: str) -> list[AssetEntry]:
        return [e for e in self.model.entries if e.kind == kind]

    def match_aliases(self, text: str, kind: str) -> list[tuple[AssetEntry, str, int]]:
        """(entry, matched alias, position) for every alias of `kind` found in `text` (lower-case, whole words;
        the longest alias wins when aliases overlap)."""
        found = []
        for e in self.of_kind(kind):
            for alias in sorted(e.aliases, key=len, reverse=True):
                m = re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", text)
                if m:
                    found.append((e, alias, m.start()))
                    break
        return sorted(found, key=lambda t: t[2])


def load_registry(path: str | Path | None = None) -> Registry:
    data = yaml.safe_load(Path(path or DEFAULT_REGISTRY).read_text(encoding="utf-8"))
    return Registry(AssetRegistry.model_validate(data))
