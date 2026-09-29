from __future__ import annotations

import collections
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .parsers import ControllerLog, deduplicate_state


def wrap_degrees(value):
    return (value + 180.0) % 360.0 - 180.0


def wrap_radians(value):
    return (value + np.pi) % (2.0 * np.pi) - np.pi


def rmse(values) -> float:
    array = np.asarray(values, dtype=float)
    return float(np.sqrt(np.mean(array**2))) if len(array) else math.nan


def p95(values) -> float:
    array = np.asarray(values, dtype=float)
    return float(np.percentile(array, 95)) if len(array) else math.nan


def centered_trajectory_speed(
    path: Path,
    half_window_s: float = 1.0,
) -> np.ndarray:
    """Estimate planar speed from an RTK trajectory by centered interpolation."""

    if half_window_s <= 0.0:
        raise ValueError("half_window_s must be positive")
    trajectory = pd.read_csv(path)
    required = {"time", "x", "y"}
    missing = required - set(trajectory.columns)
    if missing:
        raise ValueError(
            f"Missing RTK trajectory columns in {path}: {', '.join(sorted(missing))}"
        )
    trajectory = (
        trajectory.dropna(subset=["time", "x", "y"])
        .sort_values("time")
        .drop_duplicates("time", keep="last")
    )
    if len(trajectory) < 2:
        raise ValueError(f"Insufficient RTK trajectory samples in {path}")

    time = trajectory["time"].to_numpy(dtype=float)
    x = trajectory["x"].to_numpy(dtype=float)
    y = trajectory["y"].to_numpy(dtype=float)
    before = time - half_window_s
    after = time + half_window_s
    valid = (before >= time[0]) & (after <= time[-1])
    if not np.any(valid):
        raise ValueError(
            f"No samples support a centered {half_window_s:.1f} s half-window in {path}"
        )

    dx = np.interp(after[valid], time, x) - np.interp(before[valid], time, x)
    dy = np.interp(after[valid], time, y) - np.interp(before[valid], time, y)
    return np.hypot(dx, dy) / (2.0 * half_window_s)


def select_follow_segment(
    log: ControllerLog,
    desired_d_m: float = 10.0,
    desired_h_m: float = 30.0,
) -> tuple[pd.Series, float]:
    if log.tasks.empty:
        raise ValueError(f"No task records in {log.path}")
    selected_index = None
    for index, row in log.tasks.iterrows():
        if math.isclose(float(row["desired_d_m"]), desired_d_m) and math.isclose(
            float(row["desired_h_m"]), desired_h_m
        ):
            selected_index = index
            break
    if selected_index is None:
        raise ValueError(f"No D={desired_d_m}, h={desired_h_m} task in {log.path}")
    task = log.tasks.loc[selected_index]
    later = log.tasks[
        log.tasks["wall_elapsed_s"] > float(task["wall_elapsed_s"])
    ]
    end_s = (
        float(later.iloc[0]["wall_elapsed_s"])
        if not later.empty
        else log.duration_s
    )
    return task, end_s


def summarize_tracking_trials(
    logs: list[tuple[str, ControllerLog, Path]],
    trim_s: float = 10.0,
    speed_half_window_s: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    paper_rows: list[dict] = []
    audit_rows: list[dict] = []
    for label, log, speed_path in logs:
        task, segment_end = select_follow_segment(log)
        start = float(task["wall_elapsed_s"]) + trim_s
        samples = log.positions[
            (log.positions["wall_elapsed_s"] >= start)
            & (log.positions["wall_elapsed_s"] < segment_end)
        ].copy()
        if samples.empty:
            raise ValueError(f"No position samples for {label}")
        effective_start = float(samples["wall_elapsed_s"].iloc[0])
        effective_end = float(samples["wall_elapsed_s"].iloc[-1])

        yaw = np.deg2rad(samples["ugv_yaw_deg"].to_numpy(dtype=float))
        desired_x = samples["ugv_x_m"].to_numpy(dtype=float) + float(
            task["desired_d_m"]
        ) * np.cos(yaw)
        desired_y = samples["ugv_y_m"].to_numpy(dtype=float) + float(
            task["desired_d_m"]
        ) * np.sin(yaw)
        planar_error = np.hypot(
            samples["uav_x_m"].to_numpy(dtype=float) - desired_x,
            samples["uav_y_m"].to_numpy(dtype=float) - desired_y,
        )
        height_error = (
            samples["height_m"].to_numpy(dtype=float)
            - float(task["desired_h_m"])
        )
        yaw_error = wrap_degrees(
            samples["uav_yaw_deg"].to_numpy(dtype=float)
            - samples["ugv_yaw_deg"].to_numpy(dtype=float)
        )
        remote_times = log.remote_pos.loc[
            (log.remote_pos["wall_elapsed_s"] >= effective_start)
            & (log.remote_pos["wall_elapsed_s"] <= effective_end),
            "wall_elapsed_s",
        ].drop_duplicates()
        lora_times = log.lora.loc[
            (log.lora["wall_elapsed_s"] >= effective_start)
            & (log.lora["wall_elapsed_s"] <= effective_end),
            "wall_elapsed_s",
        ].drop_duplicates()
        dual_times = np.sort(
            np.unique(
                np.concatenate(
                    [
                        remote_times.to_numpy(dtype=float),
                        lora_times.to_numpy(dtype=float),
                    ]
                )
            )
        )
        dual_gaps = np.diff(dual_times)
        speed_kmh = centered_trajectory_speed(
            speed_path, speed_half_window_s
        ) * 3.6

        paper_rows.append(
            {
                "trial": label,
                "duration_s": effective_end - effective_start,
                "relative_distance_median_m": float(
                    np.median(samples["distance_m"])
                ),
                "relative_distance_p95_m": p95(samples["distance_m"]),
                "planar_rmse_m": rmse(planar_error),
                "planar_p95_m": p95(planar_error),
                "height_rmse_m": rmse(height_error),
                "yaw_mae_deg": float(np.mean(np.abs(yaw_error))),
                "dual_source_p95_gap_s": p95(dual_gaps),
                "mean_speed_kmh": float(np.mean(speed_kmh)),
                "p95_speed_kmh": p95(speed_kmh),
            }
        )
        audit_rows.append(
            {
                "trial": label,
                "source_file": log.path.name,
                "task_state_time_s": task["state_time_s"],
                "window_wall_start_s": effective_start,
                "window_wall_end_s": effective_end,
                "samples": len(samples),
                "planar_rmse_m": rmse(planar_error),
                "planar_p95_m": p95(planar_error),
                "remote_updates": len(remote_times),
                "lora_updates": len(lora_times),
                "dual_updates": len(dual_times),
                "dual_max_gap_s": (
                    float(np.max(dual_gaps)) if len(dual_gaps) else math.nan
                ),
                "speed_source_file": speed_path.name,
                "speed_samples": len(speed_kmh),
                "mean_speed_kmh": float(np.mean(speed_kmh)),
                "p95_speed_kmh": p95(speed_kmh),
            }
        )
    return pd.DataFrame(paper_rows), pd.DataFrame(audit_rows)


def reconstruct_outer_loop(
    log: ControllerLog,
    leading_distance_m: float,
) -> pd.DataFrame:
    uav = deduplicate_state(log.realtime_uav)[
        ["state_time_s", "x_m", "y_m"]
    ].rename(columns={"x_m": "uav_x_m", "y_m": "uav_y_m"})
    ugv = deduplicate_state(log.realtime_ugv)[
        ["state_time_s", "x_m", "y_m"]
    ].rename(
        columns={
            "state_time_s": "ugv_pos_time_s",
            "x_m": "ugv_x_m",
            "y_m": "ugv_y_m",
        }
    )
    yaw = deduplicate_state(log.payload_ugv_yaw)[
        ["state_time_s", "yaw_deg"]
    ].rename(
        columns={
            "state_time_s": "ugv_yaw_time_s",
            "yaw_deg": "ugv_yaw_deg",
        }
    )
    if uav.empty or ugv.empty or yaw.empty:
        raise ValueError(f"Missing response-model states in {log.path}")
    aligned = pd.merge_asof(
        uav.sort_values("state_time_s"),
        ugv.sort_values("ugv_pos_time_s"),
        left_on="state_time_s",
        right_on="ugv_pos_time_s",
        direction="backward",
    )
    aligned = pd.merge_asof(
        aligned.sort_values("state_time_s"),
        yaw.sort_values("ugv_yaw_time_s"),
        left_on="state_time_s",
        right_on="ugv_yaw_time_s",
        direction="backward",
    ).dropna()
    yaw_rad = np.deg2rad(aligned["ugv_yaw_deg"].to_numpy(dtype=float))
    aligned["ugv_yaw_rad"] = yaw_rad
    aligned["x_des_m"] = (
        aligned["ugv_x_m"] + leading_distance_m * np.cos(yaw_rad)
    )
    aligned["y_des_m"] = (
        aligned["ugv_y_m"] + leading_distance_m * np.sin(yaw_rad)
    )
    aligned["state_age_pos_s"] = (
        aligned["state_time_s"] - aligned["ugv_pos_time_s"]
    )
    aligned["state_age_yaw_s"] = (
        aligned["state_time_s"] - aligned["ugv_yaw_time_s"]
    )
    aligned["error_x_m"] = aligned["x_des_m"] - aligned["uav_x_m"]
    aligned["error_y_m"] = aligned["y_des_m"] - aligned["uav_y_m"]
    return aligned.reset_index(drop=True)


def fit_axis(series: pd.DataFrame, axis: str) -> dict:
    state = series[f"uav_{axis}_m"].to_numpy(dtype=float)
    desired = series[f"{axis}_des_m"].to_numpy(dtype=float)
    time = series["state_time_s"].to_numpy(dtype=float)
    p0, p1, u0, dt = state[:-1], state[1:], desired[:-1], np.diff(time)
    valid = (
        np.isfinite(p0)
        & np.isfinite(p1)
        & np.isfinite(u0)
        & np.isfinite(dt)
        & (dt > 0.05)
        & (dt < 0.25)
    )
    p0, p1, u0, dt = p0[valid], p1[valid], u0[valid], dt[valid]
    residual_state = p0 - u0
    next_state = p1 - u0
    alpha = float(
        np.dot(residual_state, next_state)
        / np.dot(residual_state, residual_state)
    )
    alpha = float(np.clip(alpha, 1e-6, 0.999999))
    residual = p1 - (alpha * p0 + (1.0 - alpha) * u0)
    lambdas = -np.log(alpha) / dt
    return {
        "axis": axis,
        "samples": len(residual),
        "alpha": alpha,
        "dt_median_s": float(np.median(dt)),
        "lambda_s_inv": float(np.median(lambdas)),
        "time_constant_s": float(1.0 / np.median(lambdas)),
        "rmse_m": rmse(residual),
        "p95_residual_m": p95(np.abs(residual)),
    }


def fit_planar_scalar(series: pd.DataFrame) -> dict:
    blocks = []
    for axis in ("x", "y"):
        state = series[f"uav_{axis}_m"].to_numpy(dtype=float)
        desired = series[f"{axis}_des_m"].to_numpy(dtype=float)
        time = series["state_time_s"].to_numpy(dtype=float)
        p0, p1, u0, dt = (
            state[:-1],
            state[1:],
            desired[:-1],
            np.diff(time),
        )
        valid = (
            np.isfinite(p0)
            & np.isfinite(p1)
            & np.isfinite(u0)
            & np.isfinite(dt)
            & (dt > 0.05)
            & (dt < 0.25)
        )
        blocks.append((p0[valid], p1[valid], u0[valid], dt[valid]))
    r = np.concatenate([p0 - u0 for p0, _, u0, _ in blocks])
    z = np.concatenate([p1 - u0 for _, p1, u0, _ in blocks])
    dt = np.concatenate([values[3] for values in blocks])
    alpha = float(np.clip(np.dot(r, z) / np.dot(r, r), 1e-6, 0.999999))
    residual = np.concatenate(
        [
            p1 - (alpha * p0 + (1.0 - alpha) * u0)
            for p0, p1, u0, _ in blocks
        ]
    )
    lambdas = -np.log(alpha) / dt
    return {
        "axis": "x-y scalar",
        "samples": len(residual),
        "alpha": alpha,
        "dt_median_s": float(np.median(dt)),
        "lambda_s_inv": float(np.median(lambdas)),
        "time_constant_s": float(1.0 / np.median(lambdas)),
        "rmse_m": rmse(residual),
        "p95_residual_m": p95(np.abs(residual)),
    }


def fit_response_models(
    outer_loop: pd.DataFrame, window: tuple[float, float]
) -> pd.DataFrame:
    start, end = window
    segment = outer_loop[
        (outer_loop["state_time_s"] >= start)
        & (outer_loop["state_time_s"] <= end)
    ].copy()
    return pd.DataFrame(
        [fit_axis(segment, "x"), fit_axis(segment, "y"), fit_planar_scalar(segment)]
    )


def reconstruct_delayed_reference(
    outer_loop: pd.DataFrame,
    ugv_pos: pd.DataFrame,
    ugv_yaw: pd.DataFrame,
    delay_s: float,
    leading_distance_m: float,
) -> pd.DataFrame:
    query = outer_loop[["state_time_s"]].copy()
    query["lookup_time_s"] = query["state_time_s"] - delay_s
    pos = deduplicate_state(ugv_pos)[["state_time_s", "x_m", "y_m"]].rename(
        columns={
            "state_time_s": "delayed_pos_time_s",
            "x_m": "delayed_ugv_x_m",
            "y_m": "delayed_ugv_y_m",
        }
    )
    yaw = deduplicate_state(ugv_yaw)[
        ["state_time_s", "yaw_deg"]
    ].rename(
        columns={
            "state_time_s": "delayed_yaw_time_s",
            "yaw_deg": "delayed_yaw_deg",
        }
    )
    delayed = pd.merge_asof(
        query.sort_values("lookup_time_s"),
        pos.sort_values("delayed_pos_time_s"),
        left_on="lookup_time_s",
        right_on="delayed_pos_time_s",
        direction="backward",
    )
    delayed = pd.merge_asof(
        delayed.sort_values("lookup_time_s"),
        yaw.sort_values("delayed_yaw_time_s"),
        left_on="lookup_time_s",
        right_on="delayed_yaw_time_s",
        direction="backward",
    ).dropna()
    yaw_rad = np.deg2rad(delayed["delayed_yaw_deg"].to_numpy(dtype=float))
    delayed["x_des_delay_m"] = (
        delayed["delayed_ugv_x_m"] + leading_distance_m * np.cos(yaw_rad)
    )
    delayed["y_des_delay_m"] = (
        delayed["delayed_ugv_y_m"] + leading_distance_m * np.sin(yaw_rad)
    )
    delayed["delayed_yaw_rad"] = yaw_rad
    delayed["state_age_pos_delay_s"] = (
        delayed["state_time_s"] - delayed["delayed_pos_time_s"]
    )
    delayed["state_age_yaw_delay_s"] = (
        delayed["state_time_s"] - delayed["delayed_yaw_time_s"]
    )
    return delayed


def replay_first_order(
    data: pd.DataFrame, lambda_x: float, lambda_y: float
) -> pd.DataFrame:
    data = data.sort_values("state_time_s").reset_index(drop=True).copy()
    sim_x = np.empty(len(data))
    sim_y = np.empty(len(data))
    sim_x[0] = float(data["uav_x_m"].iloc[0])
    sim_y[0] = float(data["uav_y_m"].iloc[0])
    time = data["state_time_s"].to_numpy(dtype=float)
    desired_x = data["x_des_delay_m"].to_numpy(dtype=float)
    desired_y = data["y_des_delay_m"].to_numpy(dtype=float)
    for index in range(len(data) - 1):
        dt = max(1e-6, time[index + 1] - time[index])
        ax = math.exp(-lambda_x * dt)
        ay = math.exp(-lambda_y * dt)
        sim_x[index + 1] = ax * sim_x[index] + (1.0 - ax) * desired_x[index]
        sim_y[index + 1] = ay * sim_y[index] + (1.0 - ay) * desired_y[index]
    data["sim_x_m"] = sim_x
    data["sim_y_m"] = sim_y
    data["sim_error_to_current_m"] = np.hypot(
        data["sim_x_m"] - data["x_des_m"],
        data["sim_y_m"] - data["y_des_m"],
    )
    data["reference_shift_m"] = np.hypot(
        data["x_des_delay_m"] - data["x_des_m"],
        data["y_des_delay_m"] - data["y_des_m"],
    )
    data["yaw_shift_deg"] = wrap_degrees(
        data["delayed_yaw_deg"] - data["ugv_yaw_deg"]
    )
    return data


def choose_turning_window(
    series: pd.DataFrame, width_s: float = 60.0, step_s: float = 5.0
) -> tuple[float, float]:
    time = series["state_time_s"].to_numpy(dtype=float)
    yaw = np.unwrap(series["ugv_yaw_rad"].to_numpy(dtype=float))
    yaw_rate = np.abs(np.gradient(yaw, time))
    start = float(time[0])
    limit = float(time[-1])
    best_start = start
    best_score = -1.0
    while start + width_s <= limit:
        mask = (time >= start) & (time <= start + width_s)
        score = float(np.percentile(yaw_rate[mask], 95))
        if score > best_score:
            best_score = score
            best_start = start
        start += step_s
    return best_start, best_start + width_s


def analyze_delay_sensitivity(
    log: ControllerLog,
    outer_loop: pd.DataFrame,
    window: tuple[float, float],
    delays: list[float],
    leading_distance_m: float,
    lambda_x: float,
    lambda_y: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, tuple[float, float]]:
    start, end = window
    current = outer_loop[
        (outer_loop["state_time_s"] >= start)
        & (outer_loop["state_time_s"] <= end)
    ].copy()
    turn_start, turn_end = choose_turning_window(current)
    rows: list[dict] = []
    audit_rows: list[dict] = []
    replay_rows: list[pd.DataFrame] = []
    for delay in delays:
        delayed = reconstruct_delayed_reference(
            current,
            log.realtime_ugv,
            log.payload_ugv_yaw,
            delay,
            leading_distance_m,
        )
        merged = current.merge(
            delayed.drop(columns=["lookup_time_s"]),
            on="state_time_s",
            how="inner",
        )
        replay = replay_first_order(merged, lambda_x, lambda_y)
        replay["extra_delay_s"] = delay
        replay_rows.append(replay)
        turning = replay[
            (replay["state_time_s"] >= turn_start)
            & (replay["state_time_s"] <= turn_end)
        ].copy()
        errors = turning["sim_error_to_current_m"].to_numpy(dtype=float)
        shifts = turning["reference_shift_m"].to_numpy(dtype=float)
        yaw_shifts = np.abs(turning["yaw_shift_deg"].to_numpy(dtype=float))
        rows.append(
            {
                "added_age_s": delay,
                "reference_point_shift_p95_m": p95(shifts),
                "yaw_shift_p95_deg": p95(yaw_shifts),
                "planar_p95_m": p95(errors),
                "planar_max_m": float(np.max(errors)),
            }
        )
        audit_rows.append(
            {
                "added_age_s": delay,
                "samples": len(turning),
                "turn_start_s": turn_start,
                "turn_end_s": turn_end,
                "planar_rmse_m": rmse(errors),
                "planar_p95_m": p95(errors),
                "planar_max_m": float(np.max(errors)),
            }
        )
    return (
        pd.DataFrame(rows),
        pd.DataFrame(audit_rows),
        pd.concat(replay_rows, ignore_index=True),
        (turn_start, turn_end),
    )


def communication_interval_metrics(
    state_times, start: float, end: float, timeout_s: float
) -> dict:
    """Summarize distinct source-state updates on the paper time axis."""
    if not all(math.isfinite(value) for value in (start, end, timeout_s)):
        raise ValueError("communication timing parameters must be finite")
    if end <= start:
        raise ValueError("communication window end must be after start")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")

    times = np.sort(
        np.unique(
            np.asarray(
                [time for time in state_times if start <= time <= end],
                dtype=float,
            )
        )
    )
    if len(times) < 2:
        return {
            "updates": len(times),
            "mean_interval_s": math.nan,
            "p95_interval_s": math.nan,
            "max_gap_s": math.nan,
            "timeout_rate_pct": 0.0,
        }
    gaps = np.diff(times)
    missed_duration = float(np.sum(np.maximum(0.0, gaps - timeout_s)))
    return {
        "updates": len(times),
        "mean_interval_s": float(np.mean(gaps)),
        "p95_interval_s": p95(gaps),
        "max_gap_s": float(np.max(gaps)),
        "timeout_rate_pct": 100.0 * missed_duration / (end - start),
    }


def _packet_frame(values, source: str) -> pd.DataFrame:
    """Normalize packet inputs to sensing and controller-arrival timestamps."""
    if isinstance(values, pd.DataFrame):
        frame = values.copy()
        arrival_column = (
            "arrival_time_s"
            if "arrival_time_s" in frame
            else "wall_elapsed_s"
        )
        state_column = (
            "state_time_s" if "state_time_s" in frame else arrival_column
        )
        frame = pd.DataFrame(
            {
                "arrival_time_s": frame[arrival_column],
                "state_time_s": frame[state_column],
            }
        )
    else:
        times = np.asarray(list(values), dtype=float)
        frame = pd.DataFrame(
            {
                "arrival_time_s": times,
                "state_time_s": times,
            }
        )

    frame["arrival_time_s"] = pd.to_numeric(
        frame["arrival_time_s"], errors="coerce"
    )
    frame["state_time_s"] = pd.to_numeric(
        frame["state_time_s"], errors="coerce"
    )
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    frame["source"] = source
    return (
        frame.sort_values(["arrival_time_s", "state_time_s"])
        .reset_index(drop=True)
    )


def _accepted_state_packets(frame: pd.DataFrame) -> pd.DataFrame:
    """Return packets that would advance the online per-link state cache."""
    if frame.empty:
        return frame.copy()
    state_times = frame["state_time_s"].to_numpy(dtype=float)
    previous_max = np.r_[
        float("-inf"), np.maximum.accumulate(state_times[:-1])
    ]
    return frame.loc[state_times > previous_max].copy()


def _control_slot_times(
    start: float, end: float, slot_s: float
) -> list[float]:
    """Build a stable control grid that includes the exact final endpoint."""
    tolerance = 1e-12 * max(1.0, abs(start), abs(end), abs(slot_s))
    times = [float(start)]
    index = 1
    while start + index * slot_s < end - tolerance:
        # The analysis uses 0.1 s slots. Rounding avoids values such as
        # 0.30000000000000004 leaking into CSV indices and equality checks.
        times.append(float(round(start + index * slot_s, 12)))
        index += 1
    if math.isclose(times[-1], end, rel_tol=0.0, abs_tol=tolerance):
        times[-1] = float(end)
    else:
        times.append(float(end))
    return times


def reconstruct_online_source_mode(
    remote_packets,
    lora_packets,
    start: float,
    end: float,
    timeout_s: float,
    slot_s: float,
    link_heartbeat_timeout_s: float | None = None,
    link_failure_threshold: int = 3,
    cellular_recovery_window_s: float = 1.0,
) -> pd.DataFrame:
    """Replay the online cellular-first supervisor on the arrival timeline.

    The released logs do not contain failed HTTP polls as explicit records.
    A nominal control slot without a newly arrived packet is therefore treated
    as one failed delivery opportunity. This makes the offline failure counter,
    heartbeat timeout, and cellular recovery window use the same thresholds as
    ``GvStateSupervisor`` while keeping sensing time distinct from arrival time.
    """
    if link_heartbeat_timeout_s is None:
        link_heartbeat_timeout_s = timeout_s
    numeric_parameters = (
        start,
        end,
        timeout_s,
        slot_s,
        link_heartbeat_timeout_s,
        cellular_recovery_window_s,
    )
    if not all(math.isfinite(value) for value in numeric_parameters):
        raise ValueError("source-mode timing parameters must be finite")
    if end <= start:
        raise ValueError("source-mode end must be after start")
    if timeout_s <= 0 or slot_s <= 0 or link_heartbeat_timeout_s <= 0:
        raise ValueError("source-mode timeout and slot values must be positive")
    if cellular_recovery_window_s <= 0:
        raise ValueError("cellular recovery window must be positive")
    if (
        isinstance(link_failure_threshold, bool)
        or int(link_failure_threshold) != link_failure_threshold
        or link_failure_threshold <= 0
    ):
        raise ValueError("link_failure_threshold must be a positive integer")
    link_failure_threshold = int(link_failure_threshold)

    packets = {
        "cellular": _packet_frame(remote_packets, "cellular"),
        "lora": _packet_frame(lora_packets, "lora"),
    }
    packet_indices = {"cellular": 0, "lora": 0}
    latest_packets: dict[str, dict] = {}
    last_sensed_at = {"cellular": None, "lora": None}
    last_success = {"cellular": None, "lora": None}
    failures = {"cellular": 0, "lora": 0}
    active_source = "cellular"
    cellular_recovery_since = None
    last_selected_sensed_at = None
    last_consumed_source = None
    rows: list[dict] = []
    for time in _control_slot_times(start, end, slot_s):
        arrivals_this_slot = {"cellular": False, "lora": False}
        for source, frame in packets.items():
            packet_index = packet_indices[source]
            while (
                packet_index < len(frame)
                and float(frame.iloc[packet_index]["arrival_time_s"]) <= time
            ):
                packet = frame.iloc[packet_index]
                arrival_time = float(packet["arrival_time_s"])
                sensed_at = float(packet["state_time_s"])
                last_success[source] = arrival_time
                arrivals_this_slot[source] = True
                # GvStateSupervisor.update() rejects duplicates and
                # out-of-order sensing times. They still prove transport
                # success, but must not refresh the cached state's receive
                # timestamp.
                if (
                    last_sensed_at[source] is None
                    or sensed_at > last_sensed_at[source]
                ):
                    latest_packets[source] = {
                        "source": source,
                        "arrival_time_s": arrival_time,
                        "sensed_at": sensed_at,
                    }
                    last_sensed_at[source] = sensed_at
                packet_index += 1
            packet_indices[source] = packet_index
            if arrivals_this_slot[source]:
                failures[source] = 0
            else:
                failures[source] += 1
                if source == "cellular":
                    # observe_link("cellular", False) restarts online
                    # recovery even before the failure threshold is reached.
                    cellular_recovery_since = None

        healthy = {
            source: (
                last_success[source] is not None
                and 0.0 <= time - last_success[source]
                <= link_heartbeat_timeout_s
                and failures[source] < link_failure_threshold
            )
            for source in ("cellular", "lora")
        }
        candidates = {
            source: packet
            for source, packet in latest_packets.items()
            if healthy[source]
            and 0.0 <= time - packet["arrival_time_s"] <= timeout_s
        }

        if last_selected_sensed_at is not None:
            candidates = {
                source: packet
                for source, packet in candidates.items()
                if packet["sensed_at"] >= last_selected_sensed_at
            }
        cellular = candidates.get("cellular")
        lora = candidates.get("lora")

        if active_source == "lora":
            if cellular is None:
                cellular_recovery_since = None
                selected = lora
            else:
                if cellular_recovery_since is None:
                    cellular_recovery_since = time
                cellular_recovered = (
                    time - cellular_recovery_since
                    >= cellular_recovery_window_s - 1e-12
                )
                selected = cellular if cellular_recovered else lora
        else:
            cellular_recovery_since = None
            selected = cellular if cellular is not None else lora

        source_switch = False
        selected_update = False
        if selected is not None:
            selected_source = selected["source"]
            selected_sensed_at = selected["sensed_at"]
            selected_arrival = selected["arrival_time_s"]
            source_switch = (
                last_consumed_source is not None
                and selected_source != last_consumed_source
            )
            selected_update = (
                last_selected_sensed_at is None
                or selected_sensed_at > last_selected_sensed_at
            )
            active_source = selected_source
            last_consumed_source = selected_source
            last_selected_sensed_at = selected_sensed_at
            if selected_source == "cellular":
                cellular_recovery_since = None
        else:
            selected_source = None
            selected_sensed_at = math.nan
            selected_arrival = math.nan

        cellular_packet = latest_packets.get("cellular")
        lora_packet = latest_packets.get("lora")
        rows.append(
            {
                "slot_time_s": time,
                "remote_arrival_time_s": (
                    math.nan
                    if cellular_packet is None
                    else cellular_packet["arrival_time_s"]
                ),
                "lora_arrival_time_s": (
                    math.nan
                    if lora_packet is None
                    else lora_packet["arrival_time_s"]
                ),
                "remote_state_time_s": (
                    math.nan
                    if cellular_packet is None
                    else cellular_packet["sensed_at"]
                ),
                "lora_state_time_s": (
                    math.nan
                    if lora_packet is None
                    else lora_packet["sensed_at"]
                ),
                "remote_age_s": (
                    math.nan
                    if cellular_packet is None
                    else time - cellular_packet["arrival_time_s"]
                ),
                "lora_age_s": (
                    math.nan
                    if lora_packet is None
                    else time - lora_packet["arrival_time_s"]
                ),
                "cellular_healthy": healthy["cellular"],
                "lora_healthy": healthy["lora"],
                "cellular_failures": failures["cellular"],
                "lora_failures": failures["lora"],
                "cellular_recovery_since_s": cellular_recovery_since,
                "selected_source": (
                    "5G"
                    if selected_source == "cellular"
                    else "LoRa" if selected_source == "lora" else None
                ),
                "selected_arrival_time_s": selected_arrival,
                "selected_state_time_s": selected_sensed_at,
                "selected_update": selected_update,
                "source_switch": source_switch,
            }
        )
    return pd.DataFrame(rows)


def reconstruct_source_mode(
    remote_times,
    lora_times,
    start: float,
    end: float,
    timeout_s: float,
    slot_s: float,
) -> pd.DataFrame:
    """Reproduce the source-selection rule used for the paper's Table V.

    The historical analysis works on UGV sensing timestamps. It falls back to
    LoRa only when the most recent cellular state is older than ``timeout_s``
    and LoRa has a newer state. This is intentionally distinct from replaying
    the later online link-health supervisor, which requires per-poll outcomes
    and heartbeat events that are not present in the released artifact.
    """
    remote = np.sort(np.unique(np.asarray(remote_times, dtype=float)))
    lora = np.sort(np.unique(np.asarray(lora_times, dtype=float)))
    rows: list[dict] = []
    for time in _control_slot_times(start, end, slot_s):
        remote_index = int(np.searchsorted(remote, time, side="right") - 1)
        lora_index = int(np.searchsorted(lora, time, side="right") - 1)
        remote_time = (
            float(remote[remote_index]) if remote_index >= 0 else math.nan
        )
        lora_time = (
            float(lora[lora_index]) if lora_index >= 0 else math.nan
        )
        use_lora = (
            math.isfinite(remote_time)
            and math.isfinite(lora_time)
            and time - remote_time > timeout_s
            and lora_time > remote_time
        )
        selected_time = lora_time if use_lora else remote_time
        rows.append(
            {
                "slot_time_s": time,
                "remote_state_time_s": remote_time,
                "lora_state_time_s": lora_time,
                "remote_age_s": time - remote_time,
                "lora_age_s": time - lora_time,
                "selected_source": "LoRa" if use_lora else "5G",
                "selected_state_time_s": selected_time,
            }
        )
    return pd.DataFrame(rows)


def summarize_link_performance(
    log: ControllerLog,
    window: tuple[float, float],
    timeout_s: float,
    slot_s: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    start, end = window
    remote_times = deduplicate_state(log.remote_pos)[
        "state_time_s"
    ].to_numpy(dtype=float)
    lora_times = deduplicate_state(log.lora)[
        "state_time_s"
    ].to_numpy(dtype=float)
    if len(remote_times) == 0 and len(lora_times) == 0:
        raise ValueError("No communication packets in the configured window")
    dual_times = np.unique(np.concatenate([remote_times, lora_times]))
    remote = communication_interval_metrics(
        remote_times, start, end, timeout_s
    )
    lora = communication_interval_metrics(
        lora_times, start, end, timeout_s
    )
    dual = communication_interval_metrics(
        dual_times, start, end, timeout_s
    )
    modes = reconstruct_source_mode(
        remote_times,
        lora_times,
        start,
        end,
        timeout_s,
        slot_s,
    )
    switches = int(
        (modes["selected_source"] != modes["selected_source"].shift()).sum()
        - 1
    )
    # Each row describes the selected source until the next control instant.
    # The terminal endpoint has zero duration and is excluded.
    fallback_duration = (
        float((modes.iloc[:-1]["selected_source"] == "LoRa").sum())
        * slot_s
    )
    rows = []
    for name, result in (
        ("5G-only", remote),
        ("LoRa-only", lora),
        ("Dual-mode", dual),
    ):
        rows.append(
            {
                "mode": name,
                "mean_interval_s": result["mean_interval_s"],
                "p95_interval_s": result["p95_interval_s"],
                "max_gap_s": result["max_gap_s"],
                "timeout_rate_pct": result["timeout_rate_pct"],
                "switches": switches if name == "Dual-mode" else None,
                "fallback_duration_s": (
                    fallback_duration if name == "Dual-mode" else None
                ),
            }
        )
    return pd.DataFrame(rows), modes


def prepare_aligned_communication(
    data: pd.DataFrame,
    window: tuple[float, float],
    timeout_s: float,
) -> pd.DataFrame:
    """Prepare the control-aligned stream supplied with the manuscript audit.

    The row time is the control-layer evaluation instant.  State age is kept
    exactly as logged in ``dt_5g`` and ``dt_lora``; no event-gap proxy is used
    for the strict timeout-rate column in Table V.
    """
    start, end = window
    if end <= start:
        raise ValueError("communication window end must be after start")
    if timeout_s <= 0.0:
        raise ValueError("timeout_s must be positive")
    required = {
        "time",
        "ugv_5g_time",
        "dt_5g",
        "ugv_lora_time",
        "dt_lora",
    }
    missing = required - set(data.columns)
    if missing:
        raise ValueError(
            "Missing aligned communication columns: "
            + ", ".join(sorted(missing))
        )
    result = data.loc[
        data["time"].between(start, end, inclusive="both")
    ].copy()
    if result.empty:
        raise ValueError("No aligned communication samples in configured window")
    result = result.sort_values("time").reset_index(drop=True)
    result["dual_time"] = np.maximum(
        result["ugv_5g_time"], result["ugv_lora_time"]
    )
    result["dt_dual"] = result["time"] - result["dual_time"]
    result["lora_fallback"] = (
        (result["dt_5g"] > timeout_s)
        & (result["ugv_lora_time"] > result["ugv_5g_time"])
    )
    result["selected_source"] = np.where(
        result["lora_fallback"], "LoRa", "5G"
    )
    result["both_links_stale"] = (
        (result["dt_5g"] > timeout_s)
        & (result["dt_lora"] > timeout_s)
    )
    return result


def _aligned_interval_metrics(values) -> dict[str, float]:
    times = pd.Series(values).dropna().drop_duplicates().to_numpy(dtype=float)
    gaps = np.diff(times)
    if not len(gaps):
        return {
            "mean_interval_s": math.nan,
            "p95_interval_s": math.nan,
            "max_gap_s": math.nan,
        }
    return {
        "mean_interval_s": float(np.mean(gaps)),
        "p95_interval_s": p95(gaps),
        "max_gap_s": float(np.max(gaps)),
    }


def _paper_timeout_rate(
    values,
    mission_duration_s: float,
    timeout_s: float,
    slot_s: float,
) -> float:
    """Evaluate manuscript Eq. (14) from distinct state-update timestamps."""
    times = pd.Series(values).dropna().drop_duplicates().to_numpy(dtype=float)
    gaps = np.diff(times)
    nominal_slots = math.floor(mission_duration_s / slot_s)
    if nominal_slots <= 0:
        raise ValueError("communication window has no nominal update slots")
    # A small tolerance prevents an exact decimal multiple represented just
    # below an integer from losing one missed slot under floor().
    tolerance = 1e-12 * max(1.0, timeout_s, slot_s, mission_duration_s)
    missed_slots = np.floor(
        (np.maximum(0.0, gaps - timeout_s) + tolerance) / slot_s
    ).sum()
    return 100.0 * float(missed_slots) / nominal_slots


def summarize_aligned_link_performance(
    data: pd.DataFrame,
    window: tuple[float, float],
    timeout_s: float,
    slot_s: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reproduce Table V from control-aligned GV position streams."""
    if slot_s <= 0.0:
        raise ValueError("slot_s must be positive")
    aligned = prepare_aligned_communication(data, window, timeout_s)
    switches = int(
        (aligned["selected_source"] != aligned["selected_source"].shift()).sum()
        - 1
    )
    fallback_duration = float(aligned["lora_fallback"].sum()) * slot_s
    mission_duration_s = float(window[1] - window[0])
    rows = []
    for name, time_column in (
        ("5G-only", "ugv_5g_time"),
        ("LoRa-only", "ugv_lora_time"),
        ("Dual-mode", "dual_time"),
    ):
        intervals = _aligned_interval_metrics(aligned[time_column])
        rows.append(
            {
                "mode": name,
                **intervals,
                "timeout_rate_pct": _paper_timeout_rate(
                    aligned[time_column],
                    mission_duration_s,
                    timeout_s,
                    slot_s,
                ),
                "switches": switches if name == "Dual-mode" else None,
                "fallback_duration_s": (
                    fallback_duration if name == "Dual-mode" else None
                ),
            }
        )
    return pd.DataFrame(rows), aligned


class ExtendedHeadingKalmanFilter:
    """Circular extended Kalman filter for a constant-turn-rate heading model.

    The state is ``[heading, turn_rate]``.  The transition is the standard
    constant-velocity model in the angular domain and the measurement is the
    wrapped heading ``atan2(sin(theta), cos(theta))``.  The measurement
    Jacobian is therefore ``[1, 0]`` away from the branch cut; innovations are
    always wrapped before the covariance update so a transition through
    ``+pi/-pi`` remains continuous.

    ``process_variance`` is the angular-acceleration noise intensity and
    ``measurement_variance`` is in radian squared.  ``dt`` is the elapsed time
    in seconds, so the turn-rate state is expressed in radians per second.
    """

    def __init__(
        self,
        first: float,
        process_variance: float,
        measurement_variance: float,
        reset_threshold: float | None = None,
        *,
        initial_covariance: float = 1.0,
        initial_rate_variance: float = 1.0,
    ):
        del reset_threshold  # Retained only for compatibility with old runs.
        if not math.isfinite(first):
            raise ValueError("first heading must be finite")
        if process_variance < 0:
            raise ValueError("process_variance must be non-negative")
        if measurement_variance <= 0:
            raise ValueError("measurement_variance must be positive")
        if initial_covariance < 0 or initial_rate_variance < 0:
            raise ValueError("initial covariance values must be non-negative")

        self.heading = float(wrap_radians(first))
        self.turn_rate = 0.0
        self.process_variance = float(process_variance)
        self.measurement_variance = float(measurement_variance)
        self.initial_covariance = float(initial_covariance)
        self.initial_rate_variance = float(initial_rate_variance)
        self.covariance = np.diag(
            [self.initial_covariance, self.initial_rate_variance]
        ).astype(float)
        self.last_innovation = 0.0
        self.last_gain = np.zeros(2, dtype=float)

    @property
    def x(self) -> float:
        """Compatibility view of the scalar heading state."""
        return float(wrap_radians(self.heading))

    @property
    def p(self) -> float:
        """Compatibility view of the heading marginal variance."""
        return float(self.covariance[0, 0])

    def _predict(self, dt: float) -> tuple[np.ndarray, np.ndarray]:
        transition = np.array([[1.0, dt], [0.0, 1.0]], dtype=float)
        # White angular-acceleration model, discretized over dt.
        q = self.process_variance
        process = q * np.array(
            [
                [0.25 * dt**4, 0.5 * dt**3],
                [0.5 * dt**3, dt**2],
            ],
            dtype=float,
        )
        state = transition @ np.array([self.heading, self.turn_rate])
        covariance = transition @ self.covariance @ transition.T + process
        return state, covariance

    def update_radians(self, measurement: float, dt: float = 1.0) -> float:
        if not math.isfinite(measurement):
            raise ValueError("measurement must be finite")
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be a positive finite value")

        predicted, predicted_covariance = self._predict(float(dt))
        # h(x) = atan2(sin(theta), cos(theta)); H = dh/dx locally.
        innovation = float(wrap_radians(measurement - predicted[0]))
        observation = np.array([1.0, 0.0], dtype=float)
        innovation_variance = float(
            observation @ predicted_covariance @ observation
            + self.measurement_variance
        )
        gain = (predicted_covariance @ observation) / innovation_variance
        updated = predicted + gain * innovation
        # Keep the internal heading unwrapped so a turn through +/-pi does
        # not inject a discontinuity into the turn-rate state.

        identity = np.eye(2)
        residual_map = identity - np.outer(gain, observation)
        # Joseph form keeps the covariance symmetric/positive semidefinite
        # when long heading replays accumulate floating-point error.
        covariance = (
            residual_map
            @ predicted_covariance
            @ residual_map.T
            + np.outer(gain, gain) * self.measurement_variance
        )
        self.heading = float(updated[0])
        self.turn_rate = float(updated[1])
        self.covariance = (covariance + covariance.T) * 0.5
        self.last_innovation = innovation
        self.last_gain = gain
        return float(wrap_radians(self.heading))

    def update(self, measurement: float, dt: float = 1.0) -> float:
        return self.update_radians(measurement, dt=dt)


class AutoregressiveExtendedKalmanFilter:
    """Circular EKF with an autoregressive angular-rate state model.

    The augmented state is
    ``[theta_k, omega_{k-1}, ..., omega_{k-p}]`` and evolves according to
    ``omega_k = phi_1*omega_{k-1} + ... + phi_p*omega_{k-p} + w_k`` and
    ``theta_k = theta_{k-1} + dt*omega_k``.  Modeling angular velocity rather
    than absolute angles avoids the artificial discontinuity at ``+pi/-pi``
    while retaining a genuine AR(p) companion matrix.  The wrapped heading
    observation is handled by the EKF measurement update.

    If coefficients are not supplied, a causal ridge least-squares estimate is
    updated from angular velocities seen so far; before ``p + 1`` velocity
    samples the stable coefficients ``1/p`` are used.
    """

    def __init__(
        self,
        first: float,
        order: int,
        process_variance: float,
        measurement_variance: float,
        *,
        coefficients: list[float] | tuple[float, ...] | None = None,
        initial_covariance: float = 1.0,
        ar_fit_window: int = 120,
        ar_ridge: float = 1e-6,
    ):
        if order < 1:
            raise ValueError("order must be positive")
        if not math.isfinite(first):
            raise ValueError("first heading must be finite")
        if process_variance < 0:
            raise ValueError("process_variance must be non-negative")
        if measurement_variance <= 0:
            raise ValueError("measurement_variance must be positive")
        if initial_covariance < 0:
            raise ValueError("initial_covariance must be non-negative")
        if ar_fit_window < order + 1:
            raise ValueError("ar_fit_window must be at least order + 1")
        if ar_ridge < 0:
            raise ValueError("ar_ridge must be non-negative")

        if coefficients is not None:
            if len(coefficients) != order:
                raise ValueError("coefficients length must equal order")
            coefficients = [float(value) for value in coefficients]
            if not all(math.isfinite(value) for value in coefficients):
                raise ValueError("AR coefficients must be finite")

        self.order = int(order)
        self.process_variance = float(process_variance)
        self.measurement_variance = float(measurement_variance)
        self.initial_covariance = float(initial_covariance)
        self.ar_fit_window = int(ar_fit_window)
        self.ar_ridge = float(ar_ridge)
        self.fixed_coefficients = (
            np.asarray(coefficients, dtype=float)
            if coefficients is not None
            else None
        )
        self.coefficients = (
            self.fixed_coefficients.copy()
            if self.fixed_coefficients is not None
            else np.full(self.order, 1.0 / self.order, dtype=float)
        )
        # The first component is an unwrapped heading; the remaining
        # components are lagged angular velocities in radians/second.
        self.state = np.zeros(self.order + 1, dtype=float)
        self.state[0] = float(wrap_radians(first))
        self.covariance = (
            np.eye(self.order + 1, dtype=float) * self.initial_covariance
        )
        self.measurements = [float(wrap_radians(first))]
        self.unwrapped_measurements = [float(wrap_radians(first))]
        self.angular_rates: list[float] = []
        self.last_innovation = 0.0
        self.last_gain = np.zeros(self.order + 1, dtype=float)

    @property
    def x(self) -> float:
        return float(wrap_radians(self.state[0]))

    @property
    def p(self) -> float:
        return float(self.covariance[0, 0])

    def _append_measurement(self, measurement: float, dt: float) -> None:
        wrapped = float(wrap_radians(measurement))
        previous = self.measurements[-1]
        self.measurements.append(wrapped)
        increment = float(wrap_radians(wrapped - previous))
        self.angular_rates.append(increment / dt)
        self.unwrapped_measurements.append(
            self.unwrapped_measurements[-1] + increment
        )

    def _estimate_coefficients(self) -> np.ndarray:
        if self.fixed_coefficients is not None:
            return self.fixed_coefficients.copy()
        if len(self.angular_rates) < self.order + 1:
            return np.full(self.order, 1.0 / self.order, dtype=float)

        values = np.asarray(
            self.angular_rates[-self.ar_fit_window :], dtype=float
        )
        if len(values) <= self.order:
            return np.full(self.order, 1.0 / self.order, dtype=float)
        regressors = np.vstack(
            [
                values[index - self.order : index][::-1]
                for index in range(self.order, len(values))
            ]
        )
        targets = values[self.order :]
        # Ridge regularization avoids singular normal equations for a
        # stationary or nearly constant heading sequence.
        normal = regressors.T @ regressors
        normal += self.ar_ridge * np.eye(self.order)
        try:
            coefficients = np.linalg.solve(
                normal, regressors.T @ targets
            )
        except np.linalg.LinAlgError:
            coefficients = np.full(self.order, 1.0 / self.order, dtype=float)
        if not np.all(np.isfinite(coefficients)):
            coefficients = np.full(self.order, 1.0 / self.order, dtype=float)
        # Keep the companion process stable.  Scaling only when needed
        # preserves the fitted model while preventing explosive predictions.
        coefficient_sum = float(np.sum(np.abs(coefficients)))
        if coefficient_sum >= 0.995:
            coefficients = coefficients * (0.995 / coefficient_sum)
        return coefficients

    def update_radians(self, measurement: float, dt: float = 1.0) -> float:
        if not math.isfinite(measurement):
            raise ValueError("measurement must be finite")
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be a positive finite value")
        self.coefficients = self._estimate_coefficients()
        # Estimate from samples strictly preceding this observation.  This
        # keeps the replay causal and prevents one-step look-ahead leakage.
        self._append_measurement(measurement, float(dt))

        state_size = self.order + 1
        transition = np.zeros((state_size, state_size), dtype=float)
        transition[0, 0] = 1.0
        transition[0, 1:] = float(dt) * self.coefficients
        transition[1, 1:] = self.coefficients
        if self.order > 1:
            transition[2:, 1:-1] = np.eye(self.order - 1)
        # The AR innovation enters omega_k directly and theta_k through
        # integration over dt.
        noise_map = np.zeros(state_size, dtype=float)
        noise_map[0] = float(dt)
        noise_map[1] = 1.0
        process = self.process_variance * np.outer(noise_map, noise_map)
        predicted = transition @ self.state
        predicted_covariance = (
            transition @ self.covariance @ transition.T + process
        )

        innovation = float(wrap_radians(measurement - predicted[0]))
        observation = np.zeros(state_size, dtype=float)
        observation[0] = 1.0
        innovation_variance = float(
            observation @ predicted_covariance @ observation
            + self.measurement_variance
        )
        gain = (predicted_covariance @ observation) / innovation_variance
        updated = predicted + gain * innovation
        # Keep the augmented state on one unwrapped branch.  Only the public
        # output is wrapped; wrapping lag states individually would make an
        # AR model average +pi and -pi as if they were far apart.
        identity = np.eye(state_size)
        residual_map = identity - np.outer(gain, observation)
        covariance = (
            residual_map
            @ predicted_covariance
            @ residual_map.T
            + np.outer(gain, gain) * self.measurement_variance
        )
        self.state = updated
        self.covariance = (covariance + covariance.T) * 0.5
        self.last_innovation = innovation
        self.last_gain = gain
        return float(wrap_radians(self.state[0]))

    def update(self, measurement: float, dt: float = 1.0) -> float:
        return self.update_radians(measurement, dt=dt)


# Compatibility name retained for scripts that imported the original
# paper-oriented class.  The historical ``window`` argument is ignored; the
# implementation is now the standard constant-turn-rate EKF above.
class MovingAverageKalmanFilter(ExtendedHeadingKalmanFilter):
    def __init__(
        self,
        first: float,
        window: int = 1,
        process_variance: float = 1.0,
        measurement_variance: float = 1.0,
        reset_threshold: float | None = None,
        **kwargs,
    ):
        del window
        super().__init__(
            first,
            process_variance,
            measurement_variance,
            reset_threshold,
            **kwargs,
        )


# The old AR constructor already matches the companion-state constructor.
AutoregressiveKalmanFilter = AutoregressiveExtendedKalmanFilter


class HuberKalmanFilter:
    def __init__(
        self,
        first: float,
        process_variance: float,
        measurement_variance: float,
        delta_rad: float,
    ):
        self.x = first
        self.p = 1.0
        self.q = process_variance
        self.r = measurement_variance
        self.delta = delta_rad

    def update(self, measurement: float) -> float:
        innovation = float(wrap_radians(measurement - self.x))
        innovation = float(
            np.sign(innovation) * min(abs(innovation), self.delta)
        )
        predicted_p = self.p + self.q
        gain = predicted_p / (predicted_p + self.r)
        self.x = float(wrap_radians(self.x + gain * innovation))
        self.p = (1.0 - gain) * predicted_p
        return self.x


def run_filter(values, filter_object, times=None) -> np.ndarray:
    """Replay a filter, using elapsed seconds when timestamps are supplied.

    Timed filters are constructed from the first measurement, which is
    emitted as the initialized estimate; updates begin at the second sample.
    """
    values = np.asarray(values, dtype=float)
    if not len(values):
        return np.asarray([], dtype=float)
    update = getattr(filter_object, "update_radians", None)
    if update is None:
        update = filter_object.update
    if times is not None:
        times = np.asarray(times, dtype=float)
        if len(times) != len(values):
            raise ValueError("times and values must have equal length")
        if not np.all(np.isfinite(times)):
            raise ValueError("heading timestamps must be finite")
        intervals = np.diff(times)
        if np.any(intervals <= 0):
            raise ValueError("heading timestamps must be strictly increasing")
        estimates = [float(wrap_radians(values[0]))]
        estimates.extend(
            update(float(values[index]), dt=float(intervals[index - 1]))
            for index in range(1, len(values))
        )
        return np.asarray(estimates, dtype=float)
    return np.asarray(
        [update(float(value)) for value in values], dtype=float
    )


def heading_methods(values, settings: dict, times=None) -> dict[str, np.ndarray]:
    from .runtime_filter import AdaptiveHeadingKalmanFilter

    values = np.asarray(values, dtype=float)
    first = float(values[0])
    baseline_times = (
        np.arange(len(values), dtype=float) if times is None else times
    )
    akf = settings["akf"]
    ekf = settings["ekf_labelled"]
    ekf_ar = settings["ekf_ar"]
    huber = settings["huber_kf"]
    return {
        "AKF (proposed)": run_filter(
            values,
            AdaptiveHeadingKalmanFilter(
                process_variance=akf["process_variance"],
                measurement_variance=akf["measurement_variance"],
                lower_threshold=akf["delta1_rad"],
                upper_threshold=akf["delta2_rad"],
                covariance_inflation=akf["severe_inflation"],
                initial_covariance=1.0,
            ),
        ),
        "EKF": run_filter(
            values,
            ExtendedHeadingKalmanFilter(
                first,
                ekf["process_variance"],
                ekf["measurement_variance"],
                ekf.get("reset_threshold_rad"),
                initial_covariance=ekf.get("initial_covariance", 1.0),
                initial_rate_variance=ekf.get(
                    "initial_rate_variance", 1.0
                ),
            ),
            times=baseline_times,
        ),
        "EKF-AR": run_filter(
            values,
            AutoregressiveExtendedKalmanFilter(
                first,
                ekf_ar["order"],
                ekf_ar["process_variance"],
                ekf_ar["measurement_variance"],
                coefficients=ekf_ar.get("coefficients"),
                initial_covariance=ekf_ar.get("initial_covariance", 1.0),
                ar_fit_window=ekf_ar.get("ar_fit_window", 120),
                ar_ridge=ekf_ar.get("ar_ridge", 1e-6),
            ),
            times=baseline_times,
        ),
        "Huber-based KF": run_filter(
            values,
            HuberKalmanFilter(
                first,
                huber["process_variance"],
                huber["measurement_variance"],
                math.radians(huber["delta_deg"]),
            ),
        ),
    }


@dataclass
class HeadingResults:
    table: pd.DataFrame
    by_trial: pd.DataFrame
    series: dict[str, pd.DataFrame]


def analyze_heading_filters(
    heading_dir: Path, stems: list[str], settings: dict
) -> HeadingResults:
    outlier_threshold = float(settings["outlier_threshold_deg"])
    metric_rows: list[dict] = []
    trial_series: dict[str, pd.DataFrame] = {}
    pooled: dict[str, list[np.ndarray]] = collections.defaultdict(list)
    for trial_number, stem in enumerate(stems, start=1):
        ugv_path = heading_dir / f"{stem}.csv"
        if not ugv_path.exists():
            raise FileNotFoundError(f"Missing raw UGV heading for {stem}")
        raw = (
            pd.read_csv(ugv_path)
            .dropna(subset=["time", "yaw"])
            .sort_values("time")
            .drop_duplicates("time", keep="last")
            .reset_index(drop=True)
        )
        sample_times = raw["time"].to_numpy(dtype=float)
        reference = raw["yaw"].to_numpy(dtype=float)
        estimates = heading_methods(reference, settings, times=sample_times)
        output = pd.DataFrame(
            {
                "time_s": sample_times,
                "raw_yaw_deg": np.rad2deg(reference),
            }
        )
        for method, estimate in estimates.items():
            error = np.rad2deg(wrap_radians(estimate - reference))
            absolute = np.abs(error)
            pooled[method].append(error)
            metric_rows.append(
                {
                    "trial": trial_number,
                    "trial_stem": stem,
                    "source_file": ugv_path.name,
                    "reference": "raw UGV yaw measurement",
                    "method": method,
                    "samples": len(error),
                    "mae_deg": float(np.mean(absolute)),
                    "rmse_deg": rmse(error),
                    "p95_ae_deg": p95(absolute),
                    "outlier_rate_gt_5deg_pct": float(
                        np.mean(absolute > outlier_threshold) * 100.0
                    ),
                }
            )
            output[f"{method}_yaw_deg"] = np.rad2deg(
                wrap_radians(estimate)
            )
            output[f"{method}_error_deg"] = error
        trial_series[stem] = output
    rows = []
    for method in (
        "AKF (proposed)",
        "EKF",
        "EKF-AR",
        "Huber-based KF",
    ):
        error = np.concatenate(pooled[method])
        absolute = np.abs(error)
        rows.append(
            {
                "method": method,
                "mae_deg": float(np.mean(absolute)),
                "rmse_deg": rmse(error),
                "p95_ae_deg": p95(absolute),
                "outlier_rate_gt_5deg_pct": float(
                    np.mean(absolute > outlier_threshold) * 100.0
                ),
            }
        )
    return HeadingResults(
        table=pd.DataFrame(rows),
        by_trial=pd.DataFrame(metric_rows),
        series=trial_series,
    )


# Descriptive compatibility aliases retained for older analysis notebooks.
# Paper numbering is owned by the feature modules because the current revision
# maps communication to Table V and RTK-referenced yaw comparison to Table VII.
tracking_trial_metrics = summarize_tracking_trials
outer_loop_response_models = fit_response_models
delay_sensitivity_metrics = analyze_delay_sensitivity
communication_metrics = summarize_link_performance
legacy_raw_yaw_filter_metrics = analyze_heading_filters
