from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Literal["error", "warning"]
    message: str
    field: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)
