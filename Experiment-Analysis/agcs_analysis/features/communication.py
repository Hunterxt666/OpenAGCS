from __future__ import annotations

from ..dataset import ExperimentDataset
from ..figures import (
    figure_10_from_updates,
    figure_11_from_streams,
    supplementary_communication_errors_from_reconstruction,
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
        tuple(settings["table_v_communication_window_s"]),
        settings["timeout_threshold_s"],
        settings["nominal_slot_s"],
    )
    export_table(link_summary, "table_V_communication_metrics", outputs.tables)
    source_modes.to_csv(
        outputs.intermediate / "communication_source_modes.csv", index=False
    )

    figures: list[int] = []
    if generate_figures:
        figure_10_from_updates(
            dataset.figure_10_update_streams(), outputs.figures
        )
        cellular_positions, lora_positions = (
            dataset.figure_11_position_streams()
        )
        gap_markers = figure_11_from_streams(
            cellular_positions,
            lora_positions,
            outputs.figures,
            settings["figure_11_gap_threshold_s"],
        )
        communication_errors = supplementary_communication_errors_from_reconstruction(
            dataset.supplementary_communication_errors(),
            outputs.figures,
            tuple(settings["supplementary_communication_error_window_s"]),
        )
        gap_markers.to_csv(
            outputs.intermediate / "communication_gap_markers.csv",
            index=False,
        )
        communication_errors.to_csv(
            outputs.intermediate / "communication_error_series.csv",
            index=False,
        )
        figures = [10, 11]

    return FeatureResult(
        name="communication",
        tables=["table_V_communication_metrics"],
        figures=figures,
        details={
            "requested_window_s": list(
                settings["table_v_communication_window_s"]
            ),
            "actual_window_s": [
                float(source_modes["time"].min()),
                float(source_modes["time"].max()),
            ],
            "control_samples": len(source_modes),
        },
    )
