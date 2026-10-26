from __future__ import annotations

import importlib
import json
import shutil
from pathlib import Path

from .dataset import ExperimentDataset
from .figures import configure_plots
from .models import FeatureResult, OutputPaths
from .reporting import export_timestamp_data


FEATURES = ("tracking", "communication", "heading", "platoon")


def load_feature(name: str):
    module = importlib.import_module(f".features.{name}", package=__package__)
    return module.run


def normalize_features(selected: list[str] | tuple[str, ...]) -> list[str]:
    names = list(selected)
    if not names or "all" in names:
        return list(FEATURES)
    unknown = sorted(set(names) - set(FEATURES))
    if unknown:
        raise ValueError(f"Unknown analysis feature: {', '.join(unknown)}")
    return list(dict.fromkeys(names))


def run_project(
    output_dir: Path,
    selected_features: list[str] | tuple[str, ...] = ("all",),
    generate_figures: bool = True,
    clean: bool = False,
) -> dict:
    features = normalize_features(selected_features)
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)

    outputs = OutputPaths.from_root(output_dir)
    outputs.create()
    dataset = ExperimentDataset()
    if generate_figures:
        configure_plots()

    results: list[FeatureResult] = []
    for feature in features:
        results.append(
            load_feature(feature)(dataset, outputs, generate_figures)
        )

    export_timestamp_data(dataset.loaded_controllers, outputs.intermediate)
    summary = {
        "features_completed": [result.name for result in results],
        "tables_generated": [
            table for result in results for table in result.tables
        ],
        "figures_generated": [
            figure for result in results for figure in result.figures
        ],
        "intermediate_files": sorted(
            path.name
            for path in outputs.intermediate.iterdir()
            if path.is_file()
        ),
        "feature_details": {
            result.name: result.details
            for result in results
            if result.details
        },
        "analysis_notes": dataset.manifest["notes"],
    }
    (outputs.root / "analysis_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary
