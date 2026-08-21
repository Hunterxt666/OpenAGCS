"""RTK-course-referenced yaw-filter comparison used by paper Table IV.

The raw GV yaw remains the magnetometer-derived measurement.  Quantitative
errors use an independent course-angle reference reconstructed from the RTK
``x``/``y`` trajectory during valid moving segments.  This module is imported
by the project's ``heading`` feature; it can also be run directly for a small
standalone compatibility workflow.
"""

from __future__ import annotations

import argparse
import collections
import itertools
from pathlib import Path
from dataclasses import dataclass
from typing import Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .runtime_filter import AdaptiveHeadingKalmanFilter


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
        .sort_values("time")
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


def calibration_mask(valid_reference: np.ndarray, time: np.ndarray, fraction: float) -> np.ndarray:
    valid_times = time[valid_reference]
    if len(valid_times) == 0:
        return np.zeros_like(valid_reference, dtype=bool)
    cutoff = float(np.quantile(valid_times, fraction))
    return valid_reference & (time <= cutoff)


def prepare_reference_base(
    stem: str,
    half_window_s: float,
    min_speed_mps: float,
    calibration_fraction: float,
    ugv_dir: Path = UGV_DIR,
) -> pd.DataFrame:
    ugv = load_ugv_trial(stem, ugv_dir)
    trial = ugv[["time", "x", "y", "yaw"]].rename(columns={"yaw": "ugv_yaw_rad"}).copy()
    reference_yaw, speed, valid = course_reference_from_rtk(trial, half_window_s, min_speed_mps)
    time = trial["time"].to_numpy(dtype=float)

    trial["reference_yaw_rad"] = reference_yaw
    trial["trajectory_speed_mps"] = speed
    trial["valid_reference"] = valid
    trial["calibration_sample"] = calibration_mask(valid, time, calibration_fraction)
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
            }
            row.update(metrics_from_error(trial[f"{prefix}_error_deg"].to_numpy(dtype=float)))
            metric_rows.append(row)

    metrics_by_trial = pd.DataFrame(metric_rows)
    pooled_rows = []
    for method in METHODS:
        prefix = "Raw GV" if method == RAW_METHOD else method
        pooled_error = np.concatenate(
            [trial[f"{prefix}_error_deg"].to_numpy(dtype=float) for trial in trial_outputs.values()]
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
        measurement_yaw = base["ugv_yaw_rad"].to_numpy(dtype=float)
        reference_yaw = base["reference_yaw_rad"].to_numpy(dtype=float)
        mask = base["calibration_sample"].to_numpy(dtype=bool)
        estimate = estimate_one_method(method, measurement_yaw, {method: params})
        error = angular_error_deg(estimate, reference_yaw)
        errors.append(error[mask])
    return metrics_from_error(np.concatenate(errors))


def tune_baselines(
    reference_trials: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, dict[str, dict[str, float | int]]]:
    rows: list[dict[str, object]] = []
    selected: dict[str, dict[str, float | int]] = {}

    for method in TUNABLE_BASELINES:
        best_row: dict[str, object] | None = None
        best_params: dict[str, float | int] | None = None
        for candidate_idx, params in enumerate(baseline_candidate_params(method), start=1):
            metrics = evaluate_candidate(reference_trials, method, params)
            row: dict[str, object] = {"method": method, "candidate": candidate_idx}
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

    return pd.DataFrame(rows), selected


def run_akf_q_sensitivity(
    reference_trials: dict[str, pd.DataFrame],
    base_params: dict[str, dict[str, float | int]],
) -> pd.DataFrame:
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
    """Run the paper Table IV analysis on UGV-only RTK/yaw CSV inputs."""

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
        tuning_grid, baseline_overrides = tune_baselines(reference_trials)
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
    )


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
) -> list[dict[str, object]]:
    rows = []
    for method in FILTER_METHODS:
        params = params_by_method[method]
        row: dict[str, object] = {
            "method": method,
            "role": "proposed" if method == "AKF (proposed)" else "baseline",
            "tuning_basis": (
                "fixed from physical process-noise setting, Q sensitivity, and raw-yaw-only innovation stress test"
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
                values.append(f"{value:.3f}")
            elif isinstance(value, (int, np.integer)):
                values.append(str(int(value)))
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_reviewer_response(
    summary: pd.DataFrame,
    q_sensitivity: pd.DataFrame,
    selected_params: dict[str, dict[str, float | int]],
    motion_summary: pd.DataFrame,
    output_dir: Path,
) -> None:
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
    old_q_std_deg = float(np.rad2deg(np.sqrt(3.0)))

    response = f"""# Quantitative comparison for the yaw-estimation revision

We agree with the reviewer that using the raw magnetometer-derived GV yaw as
the quantitative reference creates a circular evaluation. We therefore replaced
the previous raw-yaw reference with an RTK-derived course-angle reference. For
each GV timestamp, the course angle is computed from the RTK trajectory over a
centered {COURSE_HALF_WINDOW_S:.1f}-s window, and only moving samples with
trajectory speed >= {COURSE_MIN_SPEED_MPS:.1f} m/s are used for MAE, RMSE, P95
absolute error, and the >5 deg deviation rate. The raw GV yaw remains in the
figure only as the measured magnetometer yaw, not as ground truth.

This reference construction provides {int(pooled_motion.valid_reference_samples)} valid moving samples out of {int(pooled_motion.total_samples)} GV samples ({pooled_motion.valid_reference_pct:.1f}%). The RTK-course motion statistics show a P95 heading step of {pooled_motion.p95_heading_step_deg:.2f} deg and a P95 yaw rate of {pooled_motion.p95_yaw_rate_deg_s:.2f} deg/s over consecutive valid samples.

{metric_table}

With this non-magnetometer reference, the proposed AKF obtains {proposed.mae_deg:.3f} deg MAE and {proposed.rmse_deg:.3f} deg RMSE. The raw magnetometer yaw itself has {raw.mae_deg:.3f} deg MAE against the RTK-course reference. The retuned EKF and EKF-AR baselines obtain {ekf.rmse_deg:.3f} deg and {ar.rmse_deg:.3f} deg RMSE, respectively, and the Huber-based robust KF obtains {robust.rmse_deg:.3f} deg RMSE.

## Process-noise sensitivity

The previous Q = 3.0 rad^2 corresponds to a one-step process standard deviation of {old_q_std_deg:.1f} deg, which is physically too permissive for a road-vehicle heading update. We therefore use Q = {selected_q:.5f} rad^2 in the revised table, corresponding to {selected_q_std_deg:.1f} deg per filter step, with nominal R = {selected_r:.5f} rad^2 ({selected_r_std_deg:.1f} deg measurement standard deviation), and report the sensitivity below.

{q_table}

## Baseline tuning disclosure

To avoid a strawman comparison, EKF, EKF-AR, and Huber-based KF are retuned with comparable offline effort. Each baseline is selected by grid search on the first {TUNING_CALIBRATION_FRACTION:.0%} of valid RTK-course samples from each trial, using RMSE as the selection criterion. The selected parameters are saved in `selected_filter_parameters.csv`, and all tried baseline candidates are saved in `baseline_tuning_grid.csv`. The final table above is then recomputed on all valid moving samples using the selected parameters.
"""
    (output_dir / "reviewer_response_quantitative.md").write_text(response, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-trials", type=int, default=4, help="Number of sorted paired UAV/GV trial files to use.")
    parser.add_argument(
        "--all-trials",
        action="store_true",
        help="Use all paired UAV/GV trial files instead of only the first --max-trials.",
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
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.trials:
        trial_stems = args.trials
    else:
        trial_stems = available_trial_stems()
        if not args.all_trials:
            trial_stems = trial_stems[: args.max_trials]

    if not trial_stems:
        raise RuntimeError(f"No UGV trial CSV files found in {UGV_DIR}")

    reference_trials = {
        stem: prepare_reference_base(
            stem,
            half_window_s=args.course_half_window_s,
            min_speed_mps=args.min_course_speed_mps,
            calibration_fraction=TUNING_CALIBRATION_FRACTION,
        )
        for stem in trial_stems
    }

    selected_overrides: dict[str, dict[str, float | int]] = {
        "AKF (proposed)": {
            "process_variance": args.akf_q,
            "measurement_variance": args.akf_r,
            "jump_threshold": np.deg2rad(args.akf_delta1_deg),
            "jump_threshold_high": np.deg2rad(args.akf_delta2_deg),
            "severe_inflation": args.akf_severe_inflation,
        },
    }
    tuning_grid = pd.DataFrame()
    if not args.skip_baseline_tuning:
        tuning_grid, baseline_overrides = tune_baselines(reference_trials)
        selected_overrides.update(baseline_overrides)

    selected_params = merged_filter_params(selected_overrides)
    metrics_by_trial, summary, aligned_outputs = compute_filter_comparison(
        trial_stems,
        reference_trials,
        selected_params,
    )
    q_sensitivity = run_akf_q_sensitivity(reference_trials, selected_params)
    motion_summary = compute_reference_motion_summary(reference_trials)

    metrics_by_trial.to_csv(OUT_DIR / "metrics_by_trial.csv", index=False)
    summary.to_csv(OUT_DIR / "summary_metrics.csv", index=False)
    q_sensitivity.to_csv(OUT_DIR / "akf_q_sensitivity.csv", index=False)
    tuning_grid.to_csv(OUT_DIR / "baseline_tuning_grid.csv", index=False)
    pd.DataFrame(parameter_rows(selected_params, tuned=not args.skip_baseline_tuning)).to_csv(
        OUT_DIR / "selected_filter_parameters.csv", index=False
    )
    motion_summary.to_csv(OUT_DIR / "reference_motion_summary.csv", index=False)

    for stem, trial in aligned_outputs.items():
        trial.to_csv(OUT_DIR / f"trajectory_reference_estimates_{stem}.csv", index=False)
        trial.to_csv(OUT_DIR / f"ugv_filter_estimates_{stem}.csv", index=False)

    plot_comparison(aligned_outputs, OUT_DIR)
    write_reviewer_response(summary, q_sensitivity, selected_params, motion_summary, OUT_DIR)

    print(f"Processed trials: {', '.join(trial_stems)}")
    print(f"Saved outputs to: {OUT_DIR}")
    print(summary.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
