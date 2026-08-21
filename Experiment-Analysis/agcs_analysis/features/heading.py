from __future__ import annotations

from ..dataset import ExperimentDataset
from ..figures import figure_12
from ..models import FeatureResult, OutputPaths
from ..reporting import export_table
from ..yaw_comparison import analyze_yaw_filters, write_reviewer_response


def run(
    dataset: ExperimentDataset,
    outputs: OutputPaths,
    generate_figures: bool,
) -> FeatureResult:
    """Reproduce paper Table IV and Figure 12 against RTK course yaw."""

    results = analyze_yaw_filters(
        dataset.heading_directory(),
        dataset.heading_stems(),
        dataset.heading_settings(),
    )
    export_table(results.table, "table_IV", outputs.tables)
    results.summary.to_csv(
        outputs.intermediate / "yaw_summary_metrics.csv", index=False
    )
    results.by_trial.to_csv(
        outputs.intermediate / "yaw_metrics_by_trial.csv", index=False
    )
    results.q_sensitivity.to_csv(
        outputs.intermediate / "yaw_akf_q_sensitivity.csv", index=False
    )
    results.tuning_grid.to_csv(
        outputs.intermediate / "yaw_baseline_tuning_grid.csv", index=False
    )
    results.selected_parameters.to_csv(
        outputs.intermediate / "yaw_selected_filter_parameters.csv",
        index=False,
    )
    results.motion_summary.to_csv(
        outputs.intermediate / "yaw_reference_motion_summary.csv",
        index=False,
    )
    for stem, series in results.series.items():
        series.to_csv(
            outputs.intermediate / f"yaw_reference_estimates_{stem}.csv",
            index=False,
        )
    write_reviewer_response(
        results.summary,
        results.q_sensitivity,
        results.selected_parameters_by_method,
        results.motion_summary,
        outputs.root,
    )

    figures: list[int] = []
    if generate_figures:
        figure_12(results, outputs.figures)
        figures = [12]

    return FeatureResult(
        name="heading",
        tables=["table_IV"],
        figures=figures,
        details={
            "reference": "RTK-derived course angle",
            "valid_moving_samples": int(
                results.table["n_samples"].iloc[0]
            ),
        },
    )
