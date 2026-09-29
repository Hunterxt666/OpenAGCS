from __future__ import annotations

import json

from ..dataset import ExperimentDataset
from ..figures import figure_14
from ..models import FeatureResult, OutputPaths
from ..reporting import export_table
from ..yaw_comparison import analyze_yaw_filters, export_yaw_tables, write_reviewer_response


def run(
    dataset: ExperimentDataset,
    outputs: OutputPaths,
    generate_figures: bool,
) -> FeatureResult:
    """Evaluate heading filters using the configured calibration/evaluation protocol."""

    results = analyze_yaw_filters(
        dataset.heading_directory(),
        dataset.heading_stems(),
        dataset.heading_settings(),
    )
    tables = export_yaw_tables(results, outputs.tables)
    export_table(results.q_sensitivity, "table_IX_akf_q_sensitivity", outputs.tables)
    tables.append("table_IX_akf_q_sensitivity")
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
    results.split_summary.to_csv(outputs.intermediate / "yaw_split_summary.csv", index=False)
    results.deployed_diagnostic.to_csv(
        outputs.intermediate / "yaw_deployed_akf_all_valid_diagnostic.csv", index=False,
    )
    (outputs.root / "heading_evaluation_protocol.json").write_text(
        json.dumps(results.protocol, indent=2), encoding="utf-8",
    )
    for stem, series in results.series.items():
        series.to_csv(
            outputs.intermediate / f"yaw_reference_estimates_{stem}.csv",
            index=False,
        )
    write_reviewer_response(results, outputs.root)

    figures: list[int] = []
    if generate_figures:
        figure_14(results, outputs.figures)
        figures = [14]

    return FeatureResult(
        name="heading",
        tables=tables,
        figures=figures,
        details={
            "reference": "RTK-derived course angle",
            "evaluation_protocol": results.protocol["evaluation_protocol"],
            "valid_moving_samples": results.protocol["sample_counts"]["valid_reference_samples"],
            "calibration_samples": results.protocol["sample_counts"]["calibration_samples"],
            "evaluation_samples": int(results.table["n_samples"].iloc[0]),
            "akf_retuned": False,
            "table_scopes": results.protocol["table_scopes"],
        },
    )
