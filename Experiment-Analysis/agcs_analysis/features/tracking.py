from __future__ import annotations

from ..dataset import ExperimentDataset
from ..figures import figure_5, figure_6, figure_7, figure_8
from ..metrics import (
    analyze_delay_sensitivity,
    fit_response_models,
    reconstruct_outer_loop,
    summarize_tracking_trials,
)
from ..models import FeatureResult, OutputPaths
from ..operational_envelope import state_age_envelope
from ..reporting import export_table


def run(
    dataset: ExperimentDataset,
    outputs: OutputPaths,
    generate_figures: bool,
) -> FeatureResult:
    """Analyze tracking accuracy, response dynamics, and delay sensitivity."""

    settings = dataset.settings
    tracking_summary, tracking_details = summarize_tracking_trials(
        dataset.tracking_trials(),
        speed_half_window_s=settings["table_i_speed_half_window_s"],
    )
    export_table(tracking_summary, "table_I", outputs.tables)
    export_table(state_age_envelope(), "table_II", outputs.tables)
    tracking_details.to_csv(
        outputs.intermediate / "tracking_trial_metrics.csv", index=False
    )

    # The outer-loop and delay analyses require the full controller record;
    # Table III uses a separate control-aligned communication CSV.
    communication_log = dataset.communication_5g()
    outer_loop = reconstruct_outer_loop(
        communication_log, settings["leading_distance_m"]
    )
    outer_loop.to_csv(
        outputs.intermediate / "outer_loop_reconstruction.csv", index=False
    )
    response_models = fit_response_models(
        outer_loop, tuple(settings["outer_loop_window_s"])
    )
    export_table(
        response_models, "outer_loop_response_models", outputs.tables
    )

    delay_summary, delay_details, replay, turning_window = (
        analyze_delay_sensitivity(
            communication_log,
            outer_loop,
            tuple(settings["delay_window_s"]),
            list(settings["delay_values_s"]),
            settings["leading_distance_m"],
            settings["outer_loop_lambda_x_s_inv"],
            settings["outer_loop_lambda_y_s_inv"],
        )
    )
    export_table(delay_summary, "delay_sensitivity", outputs.tables)
    delay_details.to_csv(
        outputs.intermediate / "delay_sensitivity_metrics.csv", index=False
    )
    replay.to_csv(
        outputs.intermediate / "delay_response_series.csv", index=False
    )

    figures: list[int] = []
    if generate_figures:
        representative = dataset.representative_controller()
        figure_5(
            representative,
            dataset.representative_uav_path(),
            outputs.figures,
        )
        figure_6(representative, outputs.figures)
        figure_7(representative, outputs.figures)
        tracking_errors = figure_8(representative, outputs.figures)
        tracking_errors.to_csv(
            outputs.intermediate / "tracking_error_series.csv", index=False
        )
        figures = [5, 6, 7, 8]

    return FeatureResult(
        name="tracking",
        tables=[
            "table_I",
            "table_II",
            "outer_loop_response_models",
            "delay_sensitivity",
        ],
        figures=figures,
        details={"turning_window_s": list(turning_window)},
    )
