"""Small serializable result types used by the agent and deterministic tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExtractionResult:
    ok: bool
    text: str = ""
    page_count: int = 0
    character_count: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConversionResult:
    survey: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    model: str = ""
    attempts: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

