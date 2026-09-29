"""RTK-course yaw comparison with fixed AKF and calibration-tuned baselines.

The raw GV yaw remains the magnetometer-derived measurement.  Quantitative
errors use an independent course-angle reference reconstructed from the RTK
``x``/``y`` trajectory during valid moving segments.  This module is imported
by the project's ``heading`` feature; it can also be run directly for a small
standalone workflow. The main-text Raw/AKF table always uses all valid samples.
The default baseline table scores the held-out suffix; the explicit legacy-paper
protocol reproduces the previous overlapping baseline evaluation.
"""

from __future__ import annotations

import argparse
import collections
import itertools
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
from dataclasses import dataclass
from typing import Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .runtime_filter import AdaptiveHeadingKalmanFilter
from .reporting import export_table


PROJECT_DIR = Path(__file__).resolve().parent.parent
UGV_DIR = PROJECT_DIR / "data" / "heading"
OUT_DIR = PROJECT_DIR / "output" / "yaw_comparison_revision"

COURSE_HALF_WINDOW_S = 1.0
COURSE_MIN_SPEED_MPS = 0.5
TUNING_CALIBRATION_FRACTION = 0.35
AKF_PROCESS_VARIANCE = 0.03
AKF_PROCESS_STD_DEG_PER_STEP = float(np.rad2deg(np.sqrt(AKF_PROCESS_VARIANCE)))
AKF_MEASUREMENT_STD_DEG = 3.0
AKF_MEASUREMENT_VARIANCE = 2.742e-3
AKF_DELTA1_DEG = 35.0
AKF_DELTA2_DEG = 140.0
AKF_SEVERE_INFLATION = 10.0
AKF_Q_GRID = [1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1, 3e-1, 1.0, 3.0]


RAW_METHOD = "Raw GV (measurement)"
FILTER_METHODS = ["AKF (proposed)", "EKF", "EKF-AR", "Huber-based KF"]
METHODS = [RAW_METHOD, *FILTER_METHODS]
TUNABLE_BASELINES = ["EKF", "EKF-AR", "Huber-based KF"]
EVALUATION_PROTOCOLS = ("held-out", "legacy-paper")

# Preserve the paper-compatible path when duplicate timestamps are present.
TIME_SORT_KIND = "quicksort"


@dataclass
class YawComparisonResults:
    """All paper and audit outputs from the four-trial comparison."""

    table: pd.DataFrame
    summary: pd.DataFrame
    by_trial: pd.DataFrame
    series: dict[str, pd.DataFrame]
    q_sensitivity: pd.DataFrame
    tuning_grid: pd.DataFrame
    selected_parameters: pd.DataFrame
    selected_parameters_by_method: dict[str, dict[str, float | int]]
    motion_summary: pd.DataFrame
    split_summary: pd.DataFrame
    deployed_diagnostic: pd.DataFrame
    protocol: dict

    @property
    def quantitative_table(self) -> pd.DataFrame:
        """Main-text Raw/AKF diagnostic, independent of the baseline scoring split."""
        columns = ["method", "mae_deg", "rmse_deg", "p95_ae_deg",
                   "outlier_rate_gt_5deg_pct"]
        table = self.deployed_diagnostic.loc[:, columns].copy()
        table["method"] = table["method"].replace({"AKF (proposed)": "AKF (deployed)"})
        return table


def export_yaw_tables(results: YawComparisonResults, output_dir: Path) -> list[str]:
    """Export the current manuscript's main-text and appendix table scopes."""
    tables = {
        "table_VII_yaw_filter_quantitative": results.quantitative_table,
        "table_XII_yaw_filter_baselines": results.table,
    }
    for name, table in tables.items():
        export_table(table, name, output_dir)
    return list(tables)


def wrap_angle_rad(angle: np.ndarray | float) -> np.ndarray | float:
    return (angle + np.pi) % (2.0 * np.pi) - np.pi


def angular_error_deg(estimate_rad: np.ndarray, reference_rad: np.ndarray) -> np.ndarray:
    return np.rad2deg(wrap_angle_rad(estimate_rad - reference_rad))


def drop_duplicate_time(df: pd.DataFrame) -> pd.DataFrame:
    required = ["time", "yaw"]
    if "x" in df.columns and "y" in df.columns:
        required += ["x", "y"]
    return (
        df.dropna(subset=required)
        .sort_values("time", kind=TIME_SORT_KIND)
        .drop_duplicates(subset=["time"], keep="last")
        .reset_index(drop=True)
    )


def interpolate_reference_yaw(
    reference_time: np.ndarray,
    reference_yaw_rad: np.ndarray,
    query_time: np.ndarray,
) -> np.ndarray:
    order = np.argsort(reference_time)
    t_ref = reference_time[order]
    yaw_ref = np.unwrap(reference_yaw_rad[order])
    return np.interp(query_time, t_ref, yaw_ref)


class RealTimeKalmanMovingAverageFilter:
    """Original EKF-labelled baseline used in cell 22."""

    def __init__(
        self,
        window_size: int = 20,
        process_variance: float = 1.0,
        measurement_variance: float = 150.0,
        x_first: float = 0.0,
        jump_threshold: float = 0.4,
    ) -> None:
        self.window_size = window_size
        self.process_variance = process_variance
        self.measurement_variance = measurement_variance
        self.jump_threshold = jump_threshold
        self.sliding_window: collections.deque[float] = collections.deque(maxlen=window_size)
        self.x_est = x_first
        self.p_est = 1.0

    def _kalman_update(self, measurement: float) -> float:
        x_pred = self.x_est
        p_pred = self.p_est + self.process_variance
        innovation = wrap_angle_rad(measurement - x_pred)
        k_gain = p_pred / (p_pred + self.measurement_variance)
        self.x_est = x_pred + k_gain * innovation
        self.p_est = (1.0 - k_gain) * p_pred
        return float(wrap_angle_rad(self.x_est))

    def update(self, sensor_value: float) -> float:
        self.sliding_window.append(sensor_value)
        moving_average = float(np.angle(np.mean(np.exp(1j * np.array(self.sliding_window)))))

        if abs(wrap_angle_rad(moving_average - self.x_est)) < self.jump_threshold:
            filtered_value = self._kalman_update(moving_average)
        else:
            filtered_value = moving_average
            self.x_est = moving_average

        return float(wrap_angle_rad(filtered_value))


class RealTimeKalmanARFilter:
    """Original EKF-AR-labelled baseline used in cell 22."""

    def __init__(
        self,
        ar_order: int = 3,
        process_variance: float = 0.1,
        measurement_variance: float = 10.0,
        x_first: float = 0.0,
    ) -> None:
        self.ar_order = ar_order
        self.data_storage: collections.deque[float] = collections.deque(maxlen=ar_order)
        self.process_variance = process_variance
        self.measurement_variance = measurement_variance
        self.x_est = x_first
        self.p_est = 1.0

    def _ar_predict(self) -> float:
        if len(self.data_storage) < self.ar_order:
            return self.data_storage[-1]
        values = np.unwrap(np.array(self.data_storage))
        weights = np.ones(self.ar_order) / self.ar_order
        return float(np.dot(weights, values))

    def _kalman_update(self, measurement: float) -> float:
        x_pred = self.x_est
        p_pred = self.p_est + self.process_variance
        innovation = wrap_angle_rad(measurement - x_pred)
        k_gain = p_pred / (p_pred + self.measurement_variance)
        self.x_est = x_pred + k_gain * innovation
        self.p_est = (1.0 - k_gain) * p_pred
        return float(wrap_angle_rad(self.x_est))

    def update(self, sensor_value: float) -> float:
        self.data_storage.append(sensor_value)
        ar_prediction = self._ar_predict()
        return self._kalman_update(ar_prediction)


class HuberBasedKalmanFilter:
    """
    Huber-based KF with clipped innovation.

    The update keeps the same scalar constant-heading model as the other KF
    baselines, but bounds large innovations before the measurement correction.
    This is a lightweight robust filter that remains deployable in real time.
    """

    def __init__(
        self,
        process_variance: float = AKF_PROCESS_VARIANCE,
        measurement_variance: float = 1.0,
        x_first: float = 0.0,
        huber_delta: float = np.deg2rad(20.0),
    ) -> None:
        self.x_est = x_first
        self.p_est = 1.0
        self.q = process_variance
        self.r = measurement_variance
        self.huber_delta = huber_delta
        self.clipped_updates = 0
        self.total_updates = 0

    def update(self, measurement: float) -> float:
        x_pred = self.x_est
        p_pred = self.p_est + self.q
        innovation = wrap_angle_rad(measurement - x_pred)
        abs_innovation = abs(innovation)

        if abs_innovation > self.huber_delta:
            innovation = np.sign(innovation) * self.huber_delta
            self.clipped_updates += 1

        k_gain = p_pred / (p_pred + self.r)
        self.x_est = x_pred + k_gain * innovation
        self.p_est = (1.0 - k_gain) * p_pred
        self.total_updates += 1
        return float(wrap_angle_rad(self.x_est))


DEFAULT_FILTER_PARAMS: dict[str, dict[str, float | int]] = {
    "AKF (proposed)": {
        "process_variance": AKF_PROCESS_VARIANCE,
        "measurement_variance": AKF_MEASUREMENT_VARIANCE,
        "jump_threshold": np.deg2rad(AKF_DELTA1_DEG),
        "jump_threshold_high": np.deg2rad(AKF_DELTA2_DEG),
        "severe_inflation": AKF_SEVERE_INFLATION,
    },
    "EKF": {
        "window_size": 20,
        "process_variance": 1.0,
        "measurement_variance": 150.0,
        "jump_threshold": 0.4,
    },
    "EKF-AR": {
        "ar_order": 3,
        "process_variance": 0.1,
        "measurement_variance": 10.0,
    },
    "Huber-based KF": {
        "process_variance": AKF_PROCESS_VARIANCE,
        "measurement_variance": 1.0,
        "huber_delta": np.deg2rad(20.0),
    },
}


def merged_filter_params(overrides: dict[str, dict[str, float | int]] | None = None) -> dict[str, dict[str, float | int]]:
    merged = {method: dict(params) for method, params in DEFAULT_FILTER_PARAMS.items()}
    if overrides:
        for method, params in overrides.items():
            merged.setdefault(method, {})
            merged[method].update(params)
    return merged


def make_filter(method: str, first: float, params: dict[str, float | int]):
    if method == "AKF (proposed)":
        return AdaptiveHeadingKalmanFilter(
            process_variance=float(params["process_variance"]),
            measurement_variance=float(params["measurement_variance"]),
            lower_threshold=float(params["jump_threshold"]),
            upper_threshold=float(params["jump_threshold_high"]),
            covariance_inflation=float(params["severe_inflation"]),
            initial_covariance=1.0,
        )
    if method == "EKF":
        return RealTimeKalmanMovingAverageFilter(
            window_size=int(params["window_size"]),
            process_variance=float(params["process_variance"]),
            measurement_variance=float(params["measurement_variance"]),
            x_first=first,
            jump_threshold=float(params["jump_threshold"]),
        )
    if method == "EKF-AR":
        return RealTimeKalmanARFilter(
            ar_order=int(params["ar_order"]),
            process_variance=float(params["process_variance"]),
            measurement_variance=float(params["measurement_variance"]),
            x_first=first,
        )
    if method == "Huber-based KF":
        return HuberBasedKalmanFilter(
            process_variance=float(params["process_variance"]),
            measurement_variance=float(params["measurement_variance"]),
            x_first=first,
            huber_delta=float(params["huber_delta"]),
        )
    raise ValueError(f"Unknown method: {method}")


def run_filter(values_rad: np.ndarray, filter_obj) -> np.ndarray:
    update = getattr(filter_obj, "update_radians", None)
    if update is None:
        update = filter_obj.update
    return np.array([update(float(value)) for value in values_rad], dtype=float)


def estimate_one_method(
    method: str,
    measurement_yaw_rad: np.ndarray,
    params_by_method: dict[str, dict[str, float | int]] | None = None,
) -> np.ndarray:
    if method == RAW_METHOD:
        return measurement_yaw_rad.copy()
    params = merged_filter_params(params_by_method)[method]
    first = float(measurement_yaw_rad[0])
    return run_filter(measurement_yaw_rad, make_filter(method, first, params))


def estimate_methods(
    measurement_yaw_rad: np.ndarray,
    params_by_method: dict[str, dict[str, float | int]] | None = None,
) -> dict[str, np.ndarray]:
    return {method: estimate_one_method(method, measurement_yaw_rad, params_by_method) for method in METHODS}


def metrics_from_error(error_deg: np.ndarray) -> dict[str, float]:
    finite_error = np.asarray(error_deg, dtype=float)
    finite_error = finite_error[np.isfinite(finite_error)]
    if len(finite_error) == 0:
        return {
            "n_samples": 0,
            "mae_deg": np.nan,
            "rmse_deg": np.nan,
            "median_ae_deg": np.nan,
            "p95_ae_deg": np.nan,
            "max_ae_deg": np.nan,
            "bias_deg": np.nan,
            "std_deg": np.nan,
            "outlier_rate_gt_5deg_pct": np.nan,
        }

    abs_error = np.abs(finite_error)
    return {
        "n_samples": int(len(abs_error)),
        "mae_deg": float(np.mean(abs_error)),
        "rmse_deg": float(np.sqrt(np.mean(finite_error**2))),
        "median_ae_deg": float(np.median(abs_error)),
        "p95_ae_deg": float(np.percentile(abs_error, 95)),
        "max_ae_deg": float(np.max(abs_error)),
        "bias_deg": float(np.mean(finite_error)),
        "std_deg": float(np.std(finite_error)),
        "outlier_rate_gt_5deg_pct": float(np.mean(abs_error > 5.0) * 100.0),
    }


def load_ugv_trial(stem: str, ugv_dir: Path = UGV_DIR) -> pd.DataFrame:
    """Load one UGV RTK/yaw CSV; no paired UAV input is required."""

    ugv_path = Path(ugv_dir) / f"{stem}.csv"
    if not ugv_path.exists():
        raise FileNotFoundError(ugv_path)
    return drop_duplicate_time(pd.read_csv(ugv_path))


def course_reference_from_rtk(
    ugv: pd.DataFrame,
    half_window_s: float,
    min_speed_mps: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    time = ugv["time"].to_numpy(dtype=float)
    x = ugv["x"].to_numpy(dtype=float)
    y = ugv["y"].to_numpy(dtype=float)

    before_t = time - half_window_s
    after_t = time + half_window_s
    inside_window = (before_t >= time[0]) & (after_t <= time[-1])

    x_before = np.interp(before_t, time, x)
    x_after = np.interp(after_t, time, x)
    y_before = np.interp(before_t, time, y)
    y_after = np.interp(after_t, time, y)

    dx = x_after - x_before
    dy = y_after - y_before
    displacement = np.hypot(dx, dy)
    speed = displacement / max(2.0 * half_window_s, 1e-9)
    course_yaw = wrap_angle_rad(np.arctan2(dy, dx))

    valid = inside_window & np.isfinite(course_yaw) & np.isfinite(speed) & (speed >= min_speed_mps)
    return np.asarray(course_yaw, dtype=float), np.asarray(speed, dtype=float), np.asarray(valid, dtype=bool)


def calibration_mask(
    valid_reference: np.ndarray, time: np.ndarray, fraction: float,
    protocol: str = "held-out",
) -> np.ndarray:
    if protocol not in EVALUATION_PROTOCOLS:
        raise ValueError(f"Unknown heading evaluation protocol: {protocol}")
    if not 0.0 < fraction < 1.0:
        raise ValueError("Calibration fraction must be strictly between 0 and 1")
    if not np.all(np.isfinite(time)) or np.any(np.diff(time) <= 0):
        raise ValueError("Trial timestamps must be finite and strictly increasing")
    valid_times = time[valid_reference]
    count = int(np.floor(len(valid_times) * fraction))
    if count < 1 or count >= len(valid_times):
        raise ValueError("Each trial needs nonempty calibration and evaluation subsets")
    if protocol == "legacy-paper":
        cutoff = float(np.quantile(valid_times, fraction))
        return valid_reference & (time <= cutoff)
    mask = np.zeros_like(valid_reference, dtype=bool)
    mask[np.flatnonzero(valid_reference)[:count]] = True
    return mask


def prepare_reference_base(
    stem: str,
    half_window_s: float,
    min_speed_mps: float,
    calibration_fraction: float,
    ugv_dir: Path = UGV_DIR,
    protocol: str = "held-out",
) -> pd.DataFrame:
    if not np.isfinite(half_window_s) or half_window_s <= 0:
        raise ValueError("Course half-window must be positive and finite")
    if not np.isfinite(min_speed_mps) or min_speed_mps < 0:
        raise ValueError("Minimum course speed must be non-negative and finite")
    ugv = load_ugv_trial(stem, ugv_dir)
    if ugv.empty or not np.isfinite(ugv[["time", "x", "y", "yaw"]].to_numpy()).all():
        raise ValueError(f"Trial {stem} must contain finite RTK/yaw samples")
    trial = ugv[["time", "x", "y", "yaw"]].rename(columns={"yaw": "ugv_yaw_rad"}).copy()
    reference_yaw, speed, valid = course_reference_from_rtk(trial, half_window_s, min_speed_mps)
    time = trial["time"].to_numpy(dtype=float)

    trial["reference_yaw_rad"] = reference_yaw
    trial["trajectory_speed_mps"] = speed
    trial["valid_reference"] = valid
    trial["calibration_sample"] = calibration_mask(valid, time, calibration_fraction, protocol)
    trial["held_out_sample"] = valid & ~trial["calibration_sample"].to_numpy(dtype=bool)
    trial["evaluation_sample"] = valid if protocol == "legacy-paper" else trial["held_out_sample"]
    trial["raw_yaw_deg"] = np.rad2deg(trial["ugv_yaw_rad"].to_numpy(dtype=float))
    trial["reference_yaw_deg"] = np.where(valid, np.rad2deg(wrap_angle_rad(reference_yaw)), np.nan)
    return trial.reset_index(drop=True)


def add_filter_estimates(
    base_trial: pd.DataFrame,
    params_by_method: dict[str, dict[str, float | int]] | None = None,
) -> pd.DataFrame:
    trial = base_trial.copy()
    measurement_yaw = trial["ugv_yaw_rad"].to_numpy(dtype=float)
    reference_yaw = trial["reference_yaw_rad"].to_numpy(dtype=float)
    valid = trial["valid_reference"].to_numpy(dtype=bool)

    estimates = estimate_methods(measurement_yaw, params_by_method)
    for method, estimate in estimates.items():
        error = angular_error_deg(estimate, reference_yaw)
        error[~valid] = np.nan
        prefix = method
        if method == RAW_METHOD:
            prefix = "Raw GV"
        if method == RAW_METHOD:
            trial[f"{prefix}_yaw_deg"] = np.rad2deg(estimate)
        else:
            trial[f"{prefix}_yaw_deg"] = np.rad2deg(wrap_angle_rad(estimate))
        trial[f"{prefix}_error_deg"] = error
    return trial.reset_index(drop=True)


def available_trial_stems(ugv_dir: Path = UGV_DIR) -> list[str]:
    return [path.stem for path in sorted(Path(ugv_dir).glob("*.csv"))]


def compute_filter_comparison(
    trial_stems: list[str],
    reference_trials: dict[str, pd.DataFrame],
    params_by_method: dict[str, dict[str, float | int]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    metric_rows: list[dict[str, object]] = []
    trial_outputs: dict[str, pd.DataFrame] = {}

    for trial_idx, stem in enumerate(trial_stems, start=1):
        trial = add_filter_estimates(reference_trials[stem], params_by_method)
        trial_outputs[stem] = trial
        valid_count = int(trial["valid_reference"].sum())
        total_count = int(len(trial))
        valid_pct = valid_count / max(total_count, 1) * 100.0
        calibration_count = int(trial["calibration_sample"].sum())
        evaluation = trial["evaluation_sample"].to_numpy(dtype=bool)

        for method in METHODS:
            prefix = "Raw GV" if method == RAW_METHOD else method
            row: dict[str, object] = {
                "trial": trial_idx,
                "trial_file": stem,
                "method": method,
                "total_samples": total_count,
                "valid_reference_samples": valid_count,
                "valid_reference_pct": valid_pct,
                "calibration_samples": calibration_count,
                "evaluation_samples": int(evaluation.sum()),
            }
            row.update(metrics_from_error(trial.loc[evaluation, f"{prefix}_error_deg"].to_numpy(dtype=float)))
            metric_rows.append(row)

    metrics_by_trial = pd.DataFrame(metric_rows)
    pooled_rows = []
    for method in METHODS:
        prefix = "Raw GV" if method == RAW_METHOD else method
        pooled_error = np.concatenate(
            [trial.loc[trial["evaluation_sample"], f"{prefix}_error_deg"].to_numpy(dtype=float)
             for trial in trial_outputs.values()]
        )
        row = {"method": method, "n_trials": len(trial_stems)}
        row.update(metrics_from_error(pooled_error))
        pooled_rows.append(row)
    summary = pd.DataFrame(pooled_rows)

    baseline_rmse = float(summary.loc[summary["method"] == "EKF", "rmse_deg"].iloc[0])
    baseline_mae = float(summary.loc[summary["method"] == "EKF", "mae_deg"].iloc[0])
    summary["rmse_reduction_vs_ekf_pct"] = (baseline_rmse - summary["rmse_deg"]) / baseline_rmse * 100.0
    summary["mae_reduction_vs_ekf_pct"] = (baseline_mae - summary["mae_deg"]) / baseline_mae * 100.0
    return metrics_by_trial, summary, trial_outputs


def baseline_candidate_params(method: str) -> Iterable[dict[str, float | int]]:
    if method == "EKF":
        for window_size, q, r, jump in itertools.product(
            [3, 5, 10, 20],
            [1e-4, 1e-3, 1e-2, AKF_PROCESS_VARIANCE, 1e-1, 1.0],
            [0.1, 1.0, 10.0, 100.0],
            [np.deg2rad(10.0), np.deg2rad(20.0), np.deg2rad(45.0), np.pi],
        ):
            yield {
                "window_size": window_size,
                "process_variance": q,
                "measurement_variance": r,
                "jump_threshold": jump,
            }
    elif method == "EKF-AR":
        for ar_order, q, r in itertools.product(
            [2, 3, 5, 8],
            [1e-4, 1e-3, 1e-2, AKF_PROCESS_VARIANCE, 1e-1, 1.0],
            [0.1, 1.0, 10.0, 100.0],
        ):
            yield {"ar_order": ar_order, "process_variance": q, "measurement_variance": r}
    elif method == "Huber-based KF":
        for q, r, delta_deg in itertools.product(
            [1e-4, 1e-3, 1e-2, AKF_PROCESS_VARIANCE, 1e-1, 3e-1, 1.0],
            [0.1, 1.0, 10.0],
            [5.0, 10.0, 20.0, 40.0],
        ):
            yield {
                "process_variance": q,
                "measurement_variance": r,
                "huber_delta": np.deg2rad(delta_deg),
            }
    else:
        raise ValueError(f"No tuning grid for method {method}")


def evaluate_candidate(
    reference_trials: dict[str, pd.DataFrame],
    method: str,
    params: dict[str, float | int],
) -> dict[str, float]:
    errors = []
    for base in reference_trials.values():
        # Candidate selection never processes the held-out yaw suffix.
        mask = base["calibration_sample"].to_numpy(dtype=bool)
        indices = np.flatnonzero(mask)
        if not len(indices):
            raise ValueError("Each trial must have calibration samples")
        base = base.iloc[:indices[-1] + 1]
        measurement_yaw = base["ugv_yaw_rad"].to_numpy(dtype=float)
        reference_yaw = base["reference_yaw_rad"].to_numpy(dtype=float)
        mask = base["calibration_sample"].to_numpy(dtype=bool)
        estimate = estimate_one_method(method, measurement_yaw, {method: params})
        error = angular_error_deg(estimate, reference_yaw)
        errors.append(error[mask])
    return metrics_from_error(np.concatenate(errors))


def tune_baselines(
    reference_trials: dict[str, pd.DataFrame],
    protocol: str = "held-out",
) -> tuple[pd.DataFrame, dict[str, dict[str, float | int]]]:
    """Tune the three baselines; retain the previously fixed deployed AKF."""
    if not reference_trials:
        raise ValueError("At least one heading trial is required")
    if protocol not in EVALUATION_PROTOCOLS:
        raise ValueError(f"Unknown heading evaluation protocol: {protocol}")
    rows: list[dict[str, object]] = []
    selected: dict[str, dict[str, float | int]] = {}

    for method in TUNABLE_BASELINES:
        best_row: dict[str, object] | None = None
        best_params: dict[str, float | int] | None = None
        for candidate_idx, params in enumerate(baseline_candidate_params(method), start=1):
            metrics = evaluate_candidate(reference_trials, method, params)
            if not np.isfinite(metrics["rmse_deg"]):
                raise ValueError(f"Non-finite calibration RMSE for {method}")
            row: dict[str, object] = {"method": method, "candidate": candidate_idx,
                                      "scoring_subset": "calibration", "selected": False}
            row.update(params)
            row.update(metrics)
            rows.append(row)
            if best_row is None or (
                float(row["rmse_deg"]), float(row["mae_deg"]), float(row["p95_ae_deg"])
            ) < (
                float(best_row["rmse_deg"]), float(best_row["mae_deg"]), float(best_row["p95_ae_deg"])
            ):
                best_row = row
                best_params = dict(params)
        if best_params is None:
            raise RuntimeError(f"No baseline candidates evaluated for {method}")
        selected[method] = best_params
        best_row["selected"] = True

    return pd.DataFrame(rows), selected


def run_akf_q_sensitivity(
    reference_trials: dict[str, pd.DataFrame],
    base_params: dict[str, dict[str, float | int]],
    protocol: str = "held-out",
) -> pd.DataFrame:
    """Evaluate the fixed AKF Q sweep on the full valid diagnostic subset.

    The manuscript's process-noise sensitivity table is a full-log diagnostic,
    independent of the held-out baseline comparison in Table XII. Keep the
    protocol argument for API compatibility, but do not let it change the
    sensitivity-table scoring subset.
    """
    del protocol
    rows = []
    for q in AKF_Q_GRID:
        params = merged_filter_params(base_params)
        params["AKF (proposed)"]["process_variance"] = q
        errors = []
        for base in reference_trials.values():
            measurement_yaw = base["ugv_yaw_rad"].to_numpy(dtype=float)
            reference_yaw = base["reference_yaw_rad"].to_numpy(dtype=float)
            valid = base["valid_reference"].to_numpy(dtype=bool)
            estimate = estimate_one_method("AKF (proposed)", measurement_yaw, params)
            error = angular_error_deg(estimate, reference_yaw)
            errors.append(error[valid])
        row = {
            "scoring_subset": "all-valid-diagnostic",
            "akf_q_rad2": q,
            "process_std_deg_per_step": float(np.rad2deg(np.sqrt(q))),
            "selected_for_table": bool(np.isclose(q, base_params["AKF (proposed)"]["process_variance"])),
        }
        row.update(metrics_from_error(np.concatenate(errors)))
        rows.append(row)
    return pd.DataFrame(rows)


def compute_reference_motion_summary(
    reference_trials: dict[str, pd.DataFrame],
    half_window_s: float = COURSE_HALF_WINDOW_S,
    min_speed_mps: float = COURSE_MIN_SPEED_MPS,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    pooled_rate = []
    pooled_step = []
    pooled_dt = []

    for stem, base in reference_trials.items():
        time = base["time"].to_numpy(dtype=float)
        reference = base["reference_yaw_rad"].to_numpy(dtype=float)
        valid = base["valid_reference"].to_numpy(dtype=bool)
        dt = np.diff(time)
        step = np.rad2deg(np.abs(wrap_angle_rad(np.diff(reference))))
        pair_valid = valid[1:] & valid[:-1] & np.isfinite(dt) & (dt > 0.0)
        rate = step[pair_valid] / dt[pair_valid]
        step_valid = step[pair_valid]
        dt_valid = dt[pair_valid]
        pooled_rate.append(rate)
        pooled_step.append(step_valid)
        pooled_dt.append(dt_valid)
        rows.append(
            reference_motion_row(
                stem,
                base,
                rate,
                step_valid,
                dt_valid,
                half_window_s,
                min_speed_mps,
            )
        )

    rows.append(
        reference_motion_row(
            "pooled",
            pd.concat(reference_trials.values(), ignore_index=True),
            np.concatenate(pooled_rate),
            np.concatenate(pooled_step),
            np.concatenate(pooled_dt),
            half_window_s,
            min_speed_mps,
        )
    )
    return pd.DataFrame(rows)


def analyze_yaw_filters(
    ugv_dir: Path,
    trial_stems: list[str],
    settings: dict,
) -> YawComparisonResults:
    """Evaluate fixed AKF and calibration-tuned baselines on the chosen subset."""

    if not trial_stems or len(set(trial_stems)) != len(trial_stems):
        raise ValueError("Provide at least one trial, without duplicate stems")
    protocol = settings.get("evaluation_protocol", "held-out")
    reference = settings["course_reference"]
    half_window_s = float(reference["half_window_s"])
    min_speed_mps = float(reference["min_speed_mps"])
    calibration_fraction = float(reference["calibration_fraction"])
    reference_trials = {
        stem: prepare_reference_base(
            stem,
            half_window_s=half_window_s,
            min_speed_mps=min_speed_mps,
            calibration_fraction=calibration_fraction,
            ugv_dir=ugv_dir,
            protocol=protocol,
        )
        for stem in trial_stems
    }

    akf = settings["akf"]
    selected_overrides: dict[str, dict[str, float | int]] = {
        "AKF (proposed)": {
            "process_variance": float(akf["process_variance"]),
            "measurement_variance": float(
                akf.get(
                    "measurement_variance_rad2",
                    np.deg2rad(float(akf["measurement_std_deg"])) ** 2,
                )
            ),
            "jump_threshold": float(
                np.deg2rad(float(akf["lower_threshold_deg"]))
            ),
            "jump_threshold_high": float(
                np.deg2rad(float(akf["upper_threshold_deg"]))
            ),
            "severe_inflation": float(akf["severe_inflation"]),
        }
    }
    tuning_grid = pd.DataFrame()
    tuned = bool(settings.get("tune_baselines", True))
    if tuned:
        tuning_grid, baseline_overrides = tune_baselines(reference_trials, protocol)
        selected_overrides.update(baseline_overrides)

    selected_params = merged_filter_params(selected_overrides)
    by_trial, summary, series = compute_filter_comparison(
        trial_stems,
        reference_trials,
        selected_params,
    )
    q_sensitivity = run_akf_q_sensitivity(
        reference_trials,
        selected_params,
        protocol=protocol,
    )
    motion_summary = compute_reference_motion_summary(
        reference_trials,
        half_window_s=half_window_s,
        min_speed_mps=min_speed_mps,
    )
    selected_parameters = pd.DataFrame(
        parameter_rows(
            selected_params,
            tuned=tuned,
            calibration_fraction=calibration_fraction,
            protocol=protocol,
        )
    )
    table = summary[
        [
            "method",
            "n_samples",
            "mae_deg",
            "rmse_deg",
            "median_ae_deg",
            "p95_ae_deg",
            "outlier_rate_gt_5deg_pct",
        ]
    ].copy()
    split_summary = summarize_splits(reference_trials)
    diagnostic_rows = []
    for method in [RAW_METHOD, "AKF (proposed)"]:
        prefix = "Raw GV" if method == RAW_METHOD else method
        errors = np.concatenate([trial[f"{prefix}_error_deg"].to_numpy(dtype=float)
                                 for trial in series.values()])
        diagnostic_rows.append(dict(method=method, scoring_subset="all-valid-diagnostic",
                                    **metrics_from_error(errors)))
    audit = {
        "evaluation_protocol": protocol,
        "calibration_fraction": calibration_fraction,
        "split_rule": ("timestamp quantile (historical)" if protocol == "legacy-paper"
                       else "first floor(fraction * valid_sample_count) samples in chronological order"),
        "evaluation_subset": "all-valid (overlaps calibration)" if protocol == "legacy-paper" else "held-out",
        "baseline_tuning_enabled": tuned,
        "tuned_methods": TUNABLE_BASELINES if tuned else [],
        "selection_rule": "pooled calibration RMSE; ties: MAE, P95 AE, then first candidate",
        "akf_parameter_policy": "previously fixed deployment settings; excluded from grid search",
        "state_policy": "causal replay from trial start; no reset at split; no RTK-reference filter input",
        "course_half_window_s": half_window_s,
        "course_min_speed_mps": min_speed_mps,
        "reference_note": "centered RTK reference is an offline evaluation target; adjacent windows may share positions",
        "sensitivity_subset": "all-valid-diagnostic",
        "table_scopes": {
            "table_VII_yaw_filter_quantitative": {
                "manuscript_label": "tab:yaw_filter_quantitative",
                "scoring_subset": "all-valid-diagnostic",
                "n_samples": int(split_summary["valid_reference_samples"].sum()),
                "methods": [RAW_METHOD, "AKF (deployed)"],
            },
            "table_XII_yaw_filter_baselines": {
                "manuscript_label": "tab:yaw_filter_baselines",
                "scoring_subset": "all-valid (overlaps calibration)" if protocol == "legacy-paper" else "held-out",
                "n_samples": int(split_summary["evaluation_samples"].sum()),
            },
        },
        "sample_counts": {name: int(split_summary[name].sum()) for name in
                          ["total_samples", "valid_reference_samples", "calibration_samples",
                           "held_out_samples", "evaluation_samples", "overlap_samples"]},
        "time_sort_kind": TIME_SORT_KIND,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy_disabled_cpu_features": os.environ.get("NPY_DISABLE_CPU_FEATURES", ""),
        "packages": {name: importlib.metadata.version(name)
                     for name in ["numpy", "pandas", "matplotlib"]},
        "input_sha256": {stem: hashlib.sha256((Path(ugv_dir) / f"{stem}.csv").read_bytes()).hexdigest()
                         for stem in trial_stems},
        "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "requirements_sha256": hashlib.sha256((PROJECT_DIR / "requirements.txt").read_bytes()).hexdigest(),
    }
    return YawComparisonResults(
        table=table,
        summary=summary,
        by_trial=by_trial,
        series=series,
        q_sensitivity=q_sensitivity,
        tuning_grid=tuning_grid,
        selected_parameters=selected_parameters,
        selected_parameters_by_method=selected_params,
        motion_summary=motion_summary,
        split_summary=split_summary,
        deployed_diagnostic=pd.DataFrame(diagnostic_rows),
        protocol=audit,
    )


def summarize_splits(reference_trials: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for stem, base in reference_trials.items():
        row = {"trial_file": stem, "total_samples": len(base),
               "valid_reference_samples": int(base["valid_reference"].sum()),
               "overlap_samples": int((base["calibration_sample"] & base["evaluation_sample"]).sum())}
        for name, column in [("calibration", "calibration_sample"),
                             ("held_out", "held_out_sample"), ("evaluation", "evaluation_sample")]:
            times = base.loc[base[column], "time"]
            row[f"{name}_samples"] = len(times)
            row[f"{name}_start_s"] = float(times.iloc[0])
            row[f"{name}_end_s"] = float(times.iloc[-1])
        rows.append(row)
    return pd.DataFrame(rows)


def validate_paper_environment() -> None:
    """Fail early if the documented Windows reproduction dependencies differ."""
    mismatches = []
    if platform.python_version_tuple()[:2] != ("3", "9"):
        mismatches.append(f"Python 3.9 required; found {platform.python_version()}")
    for line in (PROJECT_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, expected = line.partition("==")
        if not separator:
            raise ValueError(f"Expected a pinned requirement: {line}")
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = "not installed"
        if actual != expected:
            mismatches.append(f"{name}: expected {expected}, found {actual}")
    if mismatches:
        raise RuntimeError("Paper reproduction environment mismatch:\n" + "\n".join(mismatches))


def reference_motion_row(
    trial_file: str,
    base: pd.DataFrame,
    yaw_rate_abs_deg_s: np.ndarray,
    heading_step_abs_deg: np.ndarray,
    dt_s: np.ndarray,
    half_window_s: float,
    min_speed_mps: float,
) -> dict[str, object]:
    total = int(len(base))
    valid = int(base["valid_reference"].sum())
    row: dict[str, object] = {
        "trial_file": trial_file,
        "total_samples": total,
        "valid_reference_samples": valid,
        "valid_reference_pct": valid / max(total, 1) * 100.0,
        "speed_threshold_mps": min_speed_mps,
        "course_half_window_s": half_window_s,
        "median_dt_s": float(np.median(dt_s)) if len(dt_s) else np.nan,
        "p95_heading_step_deg": float(np.percentile(heading_step_abs_deg, 95)) if len(heading_step_abs_deg) else np.nan,
        "p99_heading_step_deg": float(np.percentile(heading_step_abs_deg, 99)) if len(heading_step_abs_deg) else np.nan,
        "max_heading_step_deg": float(np.max(heading_step_abs_deg)) if len(heading_step_abs_deg) else np.nan,
        "p95_yaw_rate_deg_s": float(np.percentile(yaw_rate_abs_deg_s, 95)) if len(yaw_rate_abs_deg_s) else np.nan,
        "p99_yaw_rate_deg_s": float(np.percentile(yaw_rate_abs_deg_s, 99)) if len(yaw_rate_abs_deg_s) else np.nan,
        "max_yaw_rate_deg_s": float(np.max(yaw_rate_abs_deg_s)) if len(yaw_rate_abs_deg_s) else np.nan,
    }
    return row


def parameter_rows(
    params_by_method: dict[str, dict[str, float | int]],
    tuned: bool,
    calibration_fraction: float = TUNING_CALIBRATION_FRACTION,
    protocol: str = "held-out",
) -> list[dict[str, object]]:
    rows = []
    for method in FILTER_METHODS:
        params = params_by_method[method]
        row: dict[str, object] = {
            "method": method,
            "role": "proposed" if method == "AKF (proposed)" else "baseline",
            "evaluation_protocol": protocol,
            "tuned_in_this_run": bool(tuned and method in TUNABLE_BASELINES),
            "tuning_basis": (
                "previously fixed deployment settings; not retuned in this comparison"
                if method == "AKF (proposed)"
                else (
                    f"grid search on first {calibration_fraction:.0%} of valid RTK-course samples"
                    if tuned
                    else "default values from the original plotting program"
                )
            ),
        }
        row.update(params)
        if "process_variance" in params:
            row["process_std_deg_per_step"] = float(np.rad2deg(np.sqrt(float(params["process_variance"]))))
        if "huber_delta" in params:
            row["huber_delta_deg"] = float(np.rad2deg(float(params["huber_delta"])))
        if "jump_threshold" in params:
            row["jump_threshold_deg"] = float(np.rad2deg(float(params["jump_threshold"])))
        if "jump_threshold_high" in params:
            row["jump_threshold_high_deg"] = float(np.rad2deg(float(params["jump_threshold_high"])))
        rows.append(row)
    return rows


def mark_calibration_region(ax, trial: pd.DataFrame) -> None:
    """Identify the unscored prefix when displaying a full held-out replay."""
    if (trial["calibration_sample"] & trial["evaluation_sample"]).any():
        return
    boundary = float(trial.loc[trial["evaluation_sample"], "time"].iloc[0])
    ax.axvspan(float(trial["time"].iloc[0]), boundary, color="0.5", alpha=0.12, zorder=0)
    ax.axvline(boundary, color="0.45", linestyle=":", linewidth=0.8)
    ax.text(0.02, 1.02, "Shaded: calibration / warm-up", transform=ax.transAxes,
            fontsize=7, va="bottom", color="0.3")


def plot_comparison(aligned_outputs: dict[str, pd.DataFrame], output_dir: Path) -> None:
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["ps.fonttype"] = 42
    plt.rcParams["axes.unicode_minus"] = False

    fig, axs = plt.subplots(2, 2, figsize=(12, 4.4))
    axs = axs.flatten()

    for idx, (_, trial) in enumerate(aligned_outputs.items()):
        if idx >= 4:
            break
        ax = axs[idx]
        mark_calibration_region(ax, trial)
        ax.plot(trial["time"], trial["raw_yaw_deg"], label="Raw GV", linestyle="dotted", alpha=0.65, linewidth=2.0, zorder=1)
        ax.plot(trial["time"], trial["reference_yaw_deg"], label="RTK course ref.", linestyle="--", linewidth=1.8, zorder=6)
        ax.plot(trial["time"], trial["EKF_yaw_deg"], label="EKF", linewidth=1.1, zorder=2)
        ax.plot(trial["time"], trial["EKF-AR_yaw_deg"], label="EKF-AR", linewidth=1.1, zorder=3)
        ax.plot(trial["time"], trial["Huber-based KF_yaw_deg"], label="Huber KF", linewidth=1.1, zorder=4)
        ax.plot(trial["time"], trial["AKF (proposed)_yaw_deg"], label="AKF", linewidth=1.8, zorder=8)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Yaw (deg)")
        ax.tick_params(axis="both", labelsize=10)

    for j in range(len(aligned_outputs), 4):
        try:
            fig.delaxes(axs[j])
        except Exception:
            pass

    panel_labels = ["a", "b", "c", "d"]
    for i, ax in enumerate(axs[:4]):
        lab = panel_labels[i] if i < len(panel_labels) else str(i + 1)
        ax.text(
            -0.08,
            1.02,
            f"({lab})",
            transform=ax.transAxes,
            fontname="Arial",
            fontsize=14,
            fontweight="bold",
            va="bottom",
            ha="left",
        )

    handles = []
    labels = []
    for ax in axs[:4]:
        h, l = ax.get_legend_handles_labels()
        for handle, label in zip(h, l):
            if label not in labels:
                handles.append(handle)
                labels.append(label)
    if labels:
        fig.legend(
            handles,
            labels,
            loc="upper center",
            bbox_to_anchor=(0.5, 0.96),
            ncol=min(len(labels), 6),
            frameon=False,
            fontsize=10.5,
        )

    fig.tight_layout()
    fig.subplots_adjust(top=0.80)
    fig.savefig(output_dir / "yaw_filters_comparison.pdf", format="pdf", dpi=600, bbox_inches="tight")
    fig.savefig(output_dir / "yaw_filters_comparison.png", dpi=300, bbox_inches="tight")
    fig.savefig(output_dir / "yaw_comparison_revision.pdf", format="pdf", dpi=600, bbox_inches="tight")
    fig.savefig(output_dir / "yaw_comparison_revision.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def markdown_table(df: pd.DataFrame, columns: list[str]) -> str:
    rounded = df[columns].copy()
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---" if c == "method" else "---:" for c in columns]) + "|"]
    for _, row in rounded.iterrows():
        values = []
        for col in columns:
            value = row[col]
            if isinstance(value, (float, np.floating)):
                values.append(f"{value:.3g}" if 0 < abs(value) < 0.001 else f"{value:.3f}")
            elif isinstance(value, (int, np.integer)):
                values.append(str(int(value)))
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_reviewer_response(
    results: YawComparisonResults,
    output_dir: Path,
) -> None:
    summary = results.summary
    q_sensitivity = results.q_sensitivity
    selected_params = results.selected_parameters_by_method
    motion_summary = results.motion_summary
    protocol = results.protocol
    table_cols = [
        "method",
        "n_samples",
        "mae_deg",
        "rmse_deg",
        "median_ae_deg",
        "p95_ae_deg",
        "outlier_rate_gt_5deg_pct",
        "rmse_reduction_vs_ekf_pct",
    ]
    ordered = summary.set_index("method").loc[METHODS].reset_index()
    metric_table = markdown_table(ordered, table_cols)

    q_cols = ["akf_q_rad2", "process_std_deg_per_step", "mae_deg", "rmse_deg", "p95_ae_deg", "selected_for_table"]
    q_table = markdown_table(q_sensitivity[q_cols], q_cols)

    proposed = summary.loc[summary["method"] == "AKF (proposed)"].iloc[0]
    raw = summary.loc[summary["method"] == RAW_METHOD].iloc[0]
    ekf = summary.loc[summary["method"] == "EKF"].iloc[0]
    ar = summary.loc[summary["method"] == "EKF-AR"].iloc[0]
    robust = summary.loc[summary["method"] == "Huber-based KF"].iloc[0]
    pooled_motion = motion_summary.loc[motion_summary["trial_file"] == "pooled"].iloc[0]
    selected_q = float(selected_params["AKF (proposed)"]["process_variance"])
    selected_q_std_deg = float(np.rad2deg(np.sqrt(selected_q)))
    selected_r = float(selected_params["AKF (proposed)"]["measurement_variance"])
    selected_r_std_deg = float(np.rad2deg(np.sqrt(selected_r)))
    split_table = markdown_table(results.split_summary, [
        "trial_file", "valid_reference_samples", "calibration_samples",
        "evaluation_samples", "overlap_samples",
    ])
    legacy = protocol["evaluation_protocol"] == "legacy-paper"
    evaluation_description = (
        "HISTORICAL REPRODUCTION ONLY: metrics use all valid samples, including calibration. "
        "These results are not held-out evaluation."
        if legacy else
        "Metrics use only the chronological suffix remaining after calibration in each trial. "
        "Calibration and evaluation samples do not overlap."
    )
    tuning_description = (
        f"The three baselines are grid-tuned on the first {protocol['calibration_fraction']:.1%} "
        "of valid samples in each trial. One parameter set per baseline is selected across "
        "all trials by pooled calibration RMSE (ties: MAE, P95 AE, then candidate order)."
        if protocol["baseline_tuning_enabled"] else
        "Baseline tuning is disabled; the original default baseline settings are evaluated."
    )

    response = f"""# Quantitative comparison for the yaw-estimation revision

Protocol: `{protocol['evaluation_protocol']}`. {evaluation_description}

The reference is the RTK-derived course angle over a centered window with
half-width {protocol['course_half_window_s']:g} s. Valid moving samples have
course speed >= {protocol['course_min_speed_mps']:g} m/s. Raw yaw is a measurement,
not ground truth. The reference is not supplied to any filter. Its centered
windows can share RTK positions near the split; this is a within-trial temporal
evaluation, not evidence of independence across trials or unseen environments.

There are {int(pooled_motion.valid_reference_samples)} valid moving samples out of
{int(pooled_motion.total_samples)} samples. Of these, {protocol['sample_counts']['calibration_samples']}
are calibration samples and {protocol['sample_counts']['evaluation_samples']} are scored.
The split rule is: {protocol['split_rule']}.

{split_table}

{metric_table}

The fixed AKF obtains {proposed.mae_deg:.3f} deg MAE and {proposed.rmse_deg:.3f} deg RMSE.
Raw yaw has {raw.mae_deg:.3f} deg MAE. EKF, EKF-AR, and Huber-KF obtain
{ekf.rmse_deg:.3f}, {ar.rmse_deg:.3f}, and {robust.rmse_deg:.3f} deg RMSE, respectively.
These comparisons characterize the deployed component and do not establish
general filter superiority or a closed-loop improvement attributable to AKF.

## Main-text Raw/AKF diagnostic

`table_VII_yaw_filter_quantitative.csv` and `.tex` reproduce the main-text table
`tab:yaw_filter_quantitative` using all {int(pooled_motion.valid_reference_samples)}
valid moving samples and the same fixed AKF replay. This full-log diagnostic is
separate from `table_XII_yaw_filter_baselines.csv` and `.tex`,
whose scoring subset follows the active protocol above.

{markdown_table(results.quantitative_table, list(results.quantitative_table.columns))}

## Process-noise sensitivity

AKF remains fixed at Q = {selected_q:g} rad^2 ({selected_q_std_deg:.1f} deg process
standard deviation), R = {selected_r:g} rad^2 ({selected_r_std_deg:.1f} deg measurement
standard deviation), lower/upper thresholds =
{np.rad2deg(selected_params['AKF (proposed)']['jump_threshold']):g}/
{np.rad2deg(selected_params['AKF (proposed)']['jump_threshold_high']):g} deg,
and inflation = {selected_params['AKF (proposed)']['severe_inflation']:g}.
The Q sweep below uses `{protocol['sensitivity_subset']}` samples for a diagnostic
only; it does not select or change AKF parameters.

{q_table}

## Baseline tuning disclosure

{tuning_description} AKF is excluded from this search: its previously fixed
deployment parameters are retained. Thus the evaluation subset is common to
all methods, but their parameter-selection procedures are not identical.
This analysis does not establish that AKF's earlier parameter development was
independent of these logs. That history must be described in the manuscript.

All filters run causally from each trial's start, including measurements without
a valid course reference, and retain their state at the split. Calibration
errors alone choose baseline parameters; evaluation errors never feed back
into parameter selection. The complete grid, settings, split timestamps,
per-sample masks, and execution metadata are exported alongside the table.
The separate all-valid Raw/AKF diagnostic must not be reported as held-out metrics.
"""
    (output_dir / "reviewer_response_quantitative.md").write_text(response, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", choices=EVALUATION_PROTOCOLS, default="held-out")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--calibration-fraction", type=float, default=TUNING_CALIBRATION_FRACTION)
    parser.add_argument("--max-trials", type=int, default=4, help="Number of manifest heading trials to use.")
    parser.add_argument(
        "--all-trials",
        action="store_true",
        help="Use all manifest heading trials instead of only the first --max-trials.",
    )
    parser.add_argument(
        "--trials",
        nargs="*",
        default=None,
        help="Optional explicit trial stems, e.g. 202410211227 202410211256.",
    )
    parser.add_argument(
        "--course-half-window-s",
        type=float,
        default=COURSE_HALF_WINDOW_S,
        help="Half-window used to compute the RTK course-angle reference.",
    )
    parser.add_argument(
        "--min-course-speed-mps",
        type=float,
        default=COURSE_MIN_SPEED_MPS,
        help="Minimum RTK trajectory speed for a valid course-angle reference.",
    )
    parser.add_argument(
        "--akf-q",
        type=float,
        default=AKF_PROCESS_VARIANCE,
        help="AKF process-noise variance used in the main table.",
    )
    parser.add_argument(
        "--akf-r",
        type=float,
        default=AKF_MEASUREMENT_VARIANCE,
        help="AKF nominal measurement-noise variance used in the main table.",
    )
    parser.add_argument(
        "--akf-delta1-deg",
        type=float,
        default=AKF_DELTA1_DEG,
        help="AKF lower innovation threshold delta1 in degrees.",
    )
    parser.add_argument(
        "--akf-delta2-deg",
        type=float,
        default=AKF_DELTA2_DEG,
        help="AKF upper innovation threshold delta2 in degrees.",
    )
    parser.add_argument(
        "--akf-severe-inflation",
        type=float,
        default=AKF_SEVERE_INFLATION,
        help="AKF measurement-variance multiplier for severe innovation outliers.",
    )
    parser.add_argument(
        "--skip-baseline-tuning",
        action="store_true",
        help="Use the default baseline parameters instead of retuning the baselines.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output or OUT_DIR / args.protocol
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.trials:
        trial_stems = args.trials
    else:
        manifest = json.loads((PROJECT_DIR / "manifest.json").read_text(encoding="utf-8"))
        trial_stems = manifest["trials"]["heading_stems"]
        if not args.all_trials:
            trial_stems = trial_stems[: args.max_trials]

    if not trial_stems:
        raise RuntimeError(f"No UGV trial CSV files found in {UGV_DIR}")

    settings = {
        "evaluation_protocol": args.protocol,
        "course_reference": {
            "half_window_s": args.course_half_window_s,
            "min_speed_mps": args.min_course_speed_mps,
            "calibration_fraction": args.calibration_fraction,
        },
        "tune_baselines": not args.skip_baseline_tuning,
        "akf": {
            "process_variance": args.akf_q,
            "measurement_variance_rad2": args.akf_r,
            "measurement_std_deg": float(np.rad2deg(np.sqrt(args.akf_r))),
            "lower_threshold_deg": args.akf_delta1_deg,
            "upper_threshold_deg": args.akf_delta2_deg,
            "severe_inflation": args.akf_severe_inflation,
        },
    }
    results = analyze_yaw_filters(UGV_DIR, trial_stems, settings)
    export_yaw_tables(results, output_dir)
    results.by_trial.to_csv(output_dir / "metrics_by_trial.csv", index=False)
    results.summary.to_csv(output_dir / "summary_metrics.csv", index=False)
    results.q_sensitivity.to_csv(output_dir / "akf_q_sensitivity.csv", index=False)
    results.tuning_grid.to_csv(output_dir / "baseline_tuning_grid.csv", index=False)
    results.selected_parameters.to_csv(output_dir / "selected_filter_parameters.csv", index=False)
    results.motion_summary.to_csv(output_dir / "reference_motion_summary.csv", index=False)
    results.split_summary.to_csv(output_dir / "split_summary.csv", index=False)
    results.deployed_diagnostic.to_csv(output_dir / "deployed_akf_all_valid_diagnostic.csv", index=False)
    (output_dir / "heading_evaluation_protocol.json").write_text(
        json.dumps(results.protocol, indent=2), encoding="utf-8",
    )
    for stem, trial in results.series.items():
        trial.to_csv(output_dir / f"trajectory_reference_estimates_{stem}.csv", index=False)
        trial.to_csv(output_dir / f"ugv_filter_estimates_{stem}.csv", index=False)

    plot_comparison(results.series, output_dir)
    write_reviewer_response(results, output_dir)

    print(f"Processed trials: {', '.join(trial_stems)}")
    print(f"Protocol: {args.protocol}")
    print(f"Saved outputs to: {output_dir}")
    print(results.summary.round(3).to_string(index=False))
    print("Main-text Raw/AKF diagnostic (all valid moving samples):")
    print(results.quantitative_table.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
