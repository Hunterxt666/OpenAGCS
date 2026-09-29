from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class OutputPaths:
    root: Path
    tables: Path
    figures: Path
    intermediate: Path

    @classmethod
    def from_root(cls, root: Path) -> "OutputPaths":
        return cls(
            root=root,
            tables=root / "tables",
            figures=root / "figures",
            intermediate=root / "intermediate",
        )

    def create(self) -> None:
        for directory in (self.tables, self.figures, self.intermediate):
            directory.mkdir(parents=True, exist_ok=True)


@dataclass
class FeatureResult:
    name: str
    tables: list[str] = field(default_factory=list)
    figures: list[int | str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
