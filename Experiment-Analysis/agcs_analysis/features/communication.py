from __future__ import annotations

from ..dataset import ExperimentDataset
from ..figures import (
    figure_9_from_updates,
    figure_10_from_streams,
    figure_11_from_reconstruction,
)
from ..metrics import summarize_aligned_link_performance
from ..models import FeatureResult, OutputPaths
from ..reporting import export_table


def run(
    dataset: ExperimentDataset,
    outputs: OutputPaths,
    generate_figures: bool,
) -> FeatureResult:
    """Analyze link intervals, source switching, fallback, and tracking impact."""

    settings = dataset.settings
    aligned_communication = dataset.communication_metrics()
    link_summary, source_modes = summarize_aligned_link_performance(
        aligned_communication,
        tuple(settings["table_iii_communication_window_s"]),
        settings["timeout_threshold_s"],
        settings["nominal_slot_s"],
    )
    export_table(link_summary, "table_III", outputs.tables)
    source_modes.to_csv(
        outputs.intermediate / "communication_source_modes.csv", index=False
    )

    figures: list[int] = []
    if generate_figures:
        figure_9_from_updates(
            dataset.figure_9_update_streams(), outputs.figures
        )
        cellular_positions, lora_positions = (
            dataset.figure_10_position_streams()
        )
        gap_markers = figure_10_from_streams(
            cellular_positions,
            lora_positions,
            outputs.figures,
            settings["figure_10_gap_threshold_s"],
        )
        communication_errors = figure_11_from_reconstruction(
            dataset.figure_11_errors(),
            outputs.figures,
            tuple(settings["figure_11_window_s"]),
        )
        gap_markers.to_csv(
            outputs.intermediate / "communication_gap_markers.csv",
            index=False,
        )
        communication_errors.to_csv(
            outputs.intermediate / "communication_error_series.csv",
            index=False,
        )
        figures = [9, 10, 11]

    return FeatureResult(
        name="communication",
        tables=["table_III"],
        figures=figures,
        details={
            "requested_window_s": list(
                settings["table_iii_communication_window_s"]
            ),
            "actual_window_s": [
                float(source_modes["time"].min()),
                float(source_modes["time"].max()),
            ],
            "control_samples": len(source_modes),
        },
    )
