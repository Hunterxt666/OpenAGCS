"""Threshold diagnostics using the yaw comparison's full-log evaluation.

Run with the pinned paper environment and NPY_DISABLE_CPU_FEATURES=AVX512F,AVX2.
The scan describes previously fixed thresholds on all valid moving samples.
Held-out errors are retained separately to audit the complete baseline table.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import yaw_comparison as yaw
from .reporting import export_table


DELTA1_GRID = (20, 25, 30, 35, 40, 45, 50)
DELTA2_GRID = (100, 120, 130, 140, 145, 150, 160, 180)
SPIKE_TRIAL = "202410211327"
SPIKE_TIME_S = 148.1


def evaluate_thresholds(trials, parameters, delta1_deg=35, delta2_deg=140):
    params = dict(parameters, jump_threshold=float(np.deg2rad(delta1_deg)),
                  jump_threshold_high=float(np.deg2rad(delta2_deg)))
    held_out_errors, all_valid_errors, regimes = [], [], []
    spike_deviation = np.nan
    for stem, trial in trials.items():
        measurements = trial["ugv_yaw_rad"].to_numpy(dtype=float)
        estimator = yaw.make_filter("AKF (proposed)", float(measurements[0]), params)
        estimates = []
        for value in measurements:
            estimates.append(estimator.update_radians(float(value)))
            innovation = abs(estimator.last_innovation)
            regimes.append(0 if innovation <= params["jump_threshold"] else
                           1 if innovation < params["jump_threshold_high"] else 2)
        estimates = np.asarray(estimates)
        error = yaw.angular_error_deg(estimates, trial["reference_yaw_rad"].to_numpy())
        held_out_errors.append(error[trial["evaluation_sample"].to_numpy(dtype=bool)])
        all_valid_errors.append(error[trial["valid_reference"].to_numpy(dtype=bool)])
        if stem == SPIKE_TRIAL:
            indices = np.flatnonzero(np.isclose(trial["time"], SPIKE_TIME_S, rtol=0, atol=1e-6))
            if len(indices) != 1 or indices[0] == 0 or indices[0] == len(trial) - 1:
                raise ValueError("Expected a single interior Trial 3 spike at 148.1 s")
            index = indices[0]
            # Local impulse diagnostic, not an RTK-course accuracy metric.
            neighbors = measurements[[index - 1, index + 1]]
            neighbor_heading = np.arctan2(np.sin(neighbors).mean(), np.cos(neighbors).mean())
            spike_deviation = abs(float(yaw.angular_error_deg(estimates[index], neighbor_heading)))
    held_out = yaw.metrics_from_error(np.concatenate(held_out_errors))
    all_valid = yaw.metrics_from_error(np.concatenate(all_valid_errors))
    regimes = np.asarray(regimes)
    return {
        "delta1_deg": delta1_deg, "delta2_deg": delta2_deg,
        "n_samples": all_valid["n_samples"],
        "mae_deg": all_valid["mae_deg"], "rmse_deg": all_valid["rmse_deg"],
        "held_out_n_samples": held_out["n_samples"],
        "held_out_mae_deg": held_out["mae_deg"],
        "held_out_rmse_deg": held_out["rmse_deg"],
        "regime_total_samples": len(regimes),
        "moderate_share_pct": 100.0 * np.mean(regimes == 1),
        "severe_share_pct": 100.0 * np.mean(regimes == 2),
        "spike_deviation_deg": spike_deviation,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=yaw.PROJECT_DIR / "output" / "threshold_sensitivity")
    args = parser.parse_args()
    yaw.validate_paper_environment()
    manifest = json.loads((yaw.PROJECT_DIR / "manifest.json").read_text(encoding="utf-8"))
    settings = manifest["heading_filter"]
    if settings["evaluation_protocol"] != "held-out":
        raise ValueError("Baseline consistency audit requires the held-out protocol")
    results = yaw.analyze_yaw_filters(yaw.UGV_DIR, manifest["trials"]["heading_stems"], settings)
    params = results.selected_parameters_by_method["AKF (proposed)"]
    lower = pd.DataFrame([evaluate_thresholds(results.series, params, delta1_deg=d)
                          for d in DELTA1_GRID])
    upper = pd.DataFrame([evaluate_thresholds(results.series, params, delta2_deg=d)
                          for d in DELTA2_GRID])
    nominal = lower.loc[lower["delta1_deg"] == 35].iloc[0]
    nominal_upper = upper.loc[upper["delta2_deg"] == 140].iloc[0]
    baseline = results.summary.set_index("method").loc["AKF (proposed)"]
    diagnostic = results.deployed_diagnostic.set_index("method").loc["AKF (proposed)"]
    for metric in ["n_samples", "mae_deg", "rmse_deg"]:
        np.testing.assert_allclose(nominal[metric], diagnostic[metric], rtol=0, atol=1e-12)
        np.testing.assert_allclose(nominal_upper[metric], diagnostic[metric], rtol=0, atol=1e-12)
        np.testing.assert_allclose(nominal[f"held_out_{metric}"], baseline[metric], rtol=0, atol=1e-12)
    args.output.mkdir(parents=True, exist_ok=True)
    yaw.export_yaw_tables(results, args.output)
    export_table(lower, "table_X_akf_delta1_sensitivity", args.output)
    export_table(upper, "table_XI_akf_delta2_sensitivity", args.output)
    results.split_summary.to_csv(args.output / "split_summary.csv", index=False)
    audit = dict(results.protocol, threshold_parameters=params,
                 threshold_error_subset="all 1807 valid moving samples, identical to Raw/AKF diagnostic",
                 threshold_regime_subset="all filter inputs, including initialization",
                 threshold_selection="none; diagnostic scan of previously fixed settings",
                 nominal_consistency_atol=1e-12)
    (args.output / "threshold_protocol.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    columns = ["delta1_deg", "delta2_deg", "n_samples", "mae_deg", "rmse_deg",
               "moderate_share_pct", "severe_share_pct", "spike_deviation_deg"]
    print(lower[columns].round(3).to_string(index=False))
    print(upper[columns].round(3).to_string(index=False))
    print("Nominal rows match complete baseline and full-log diagnostic within 1e-12 degrees.")


if __name__ == "__main__":
    main()
