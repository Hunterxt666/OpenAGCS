"""Backward-compatible entry point for the feature-oriented analysis project."""

from __future__ import annotations

from pathlib import Path

from .project import run_project


def reproduce(
    output_dir: Path,
    generate_figures: bool = True,
    clean: bool = False,
    features: list[str] | tuple[str, ...] = ("all",),
) -> dict:
    return run_project(
        output_dir=output_dir,
        selected_features=features,
        generate_figures=generate_figures,
        clean=clean,
    )
