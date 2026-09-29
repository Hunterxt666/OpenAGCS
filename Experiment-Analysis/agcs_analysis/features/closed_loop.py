from __future__ import annotations

import math

import matplotlib.pyplot as plt
import pandas as pd

from ..dataset import ExperimentDataset
from ..figures import save
from ..models import FeatureResult, OutputPaths
from ..reporting import export_table


MODES = ("5G-only", "LoRa-only", "Dual-mode")
COLORS = {"5G-only": "#1769aa", "LoRa-only": "#d97706", "Dual-mode": "#16805c"}


def _active_rows(data: pd.DataFrame) -> pd.DataFrame:
    return data.loc[data["terminated"].astype(int) == 0].copy()


def summarize_modes(trials: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compute the manuscript-facing metrics from the released flight CSVs."""
    rows: list[dict[str, str | float]] = []
    for mode in MODES:
        data = trials[mode]
        active = _active_rows(data)
        if active.empty:
            raise ValueError(f"No active UAV samples found for {mode}")
        planar_error = (active["error_x_m"] ** 2 + active["error_y_m"] ** 2) ** 0.5
        fallback_duration_s = 0.0
        if mode == "Dual-mode":
            interval = active["time_s"].shift(-1) - active["time_s"]
            fallback = (
                active["selected_source"].eq("LoRa")
                & (active["cellular_state_age_s"] > 0.3)
            )
            fallback_duration_s = float(interval.loc[fallback].clip(lower=0).sum())
        rows.append(
            {
                "mode": mode,
                "completion": "yes" if len(active) == len(data) else "no",
                "gv_path_length_m": float(data["gv_path_progress_m"].max()),
                "uav_active_duration_s": float(active["time_s"].iloc[-1] - active["time_s"].iloc[0]),
                "x_mae_m": float(active["error_x_m"].abs().mean()),
                "y_mae_m": float(active["error_y_m"].abs().mean()),
                "planar_rmse_m": float(math.sqrt((planar_error ** 2).mean())),
                "max_state_age_s": float(active["state_age_s"].max()),
                "lora_fallback_duration_s": fallback_duration_s,
            }
        )
    return pd.DataFrame(rows)


def _termination_row(data: pd.DataFrame) -> pd.Series | None:
    rows = data.loc[data["terminated"].astype(int) != 0]
    return None if rows.empty else rows.iloc[0]


def plot_errors(trials: dict[str, pd.DataFrame], output_dir) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 5.0), sharex=True)
    fields = (
        ("error_x_m", "x-axis error (m)", "(a) X-axis error"),
        ("error_y_m", "y-axis error (m)", "(b) Y-axis error"),
    )
    path_max = max(float(data["gv_path_progress_m"].max()) for data in trials.values())
    for axis, (field, ylabel, title) in zip(axes, fields):
        for mode in MODES:
            data = trials[mode]
            active = _active_rows(data)
            axis.plot(active["gv_path_progress_m"], active[field], color=COLORS[mode], linewidth=1.5, label=mode)
            terminal = _termination_row(data)
            if terminal is not None:
                axis.plot(terminal["gv_path_progress_m"], 0.0, marker="x", markersize=8, markeredgewidth=1.8, color=COLORS[mode])
        axis.axhline(0.0, color="#666666", linewidth=0.7, alpha=0.7)
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.grid(True, alpha=0.25, linewidth=0.6)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
    axes[0].legend(loc="upper right", frameon=False, ncol=3)
    axes[1].set_xlabel("GV path progress (m)")
    axes[1].set_xlim(0.0, path_max)
    fig.tight_layout()
    save(fig, output_dir, "figure_13_xy_error_comparison")


def plot_trajectories(route: pd.DataFrame, trials: dict[str, pd.DataFrame], output_dir) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12.0, 4.2), sharex=True, sharey=True)
    coordinates: list[pd.Series] = [route["x_m"], route["y_m"]]
    paths: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    for mode in MODES:
        data = trials[mode]
        gv = data if mode != "LoRa-only" else data.loc[data["gv_progress_m"] <= 84.0]
        uav = _active_rows(data)
        paths[mode] = (gv, uav)
        coordinates.extend([gv["gv_x_m"], gv["gv_y_m"], uav["uav_x_m"], uav["uav_y_m"]])
    x_values = pd.concat(coordinates[0::2], ignore_index=True)
    y_values = pd.concat(coordinates[1::2], ignore_index=True)
    x_limits = (float(x_values.min() - 20.0), float(x_values.max() + 20.0))
    y_limits = (float(y_values.min() - 15.0), float(y_values.max() + 15.0))
    for index, (axis, mode) in enumerate(zip(axes, MODES)):
        gv, uav = paths[mode]
        color = COLORS[mode]
        axis.plot(route["x_m"], route["y_m"], color="#aaaaaa", linewidth=1.0, linestyle=":", label="Measured road centerline" if index == 0 else "_nolegend_")
        axis.plot(gv["gv_x_m"], gv["gv_y_m"], color=color, linewidth=1.8, linestyle="--", label="GV path")
        axis.plot(uav["uav_x_m"], uav["uav_y_m"], color=color, linewidth=1.5, label="UAV path")
        axis.plot(gv["gv_x_m"].iloc[0], gv["gv_y_m"].iloc[0], marker="o", color="#444444", markersize=4)
        axis.plot(gv["gv_x_m"].iloc[-1], gv["gv_y_m"].iloc[-1], marker="s", color="#444444", markersize=4)
        axis.plot(uav["uav_x_m"].iloc[0], uav["uav_y_m"].iloc[0], marker="o", color=color, markersize=4)
        axis.plot(uav["uav_x_m"].iloc[-1], uav["uav_y_m"].iloc[-1], marker="s", color=color, markersize=4)
        if _termination_row(trials[mode]) is not None:
            axis.plot(uav["uav_x_m"].iloc[-1], uav["uav_y_m"].iloc[-1], marker="x", color=color, markersize=9, markeredgewidth=2.0)
        axis.set_title(f"({chr(ord('a') + index)}) {mode}")
        axis.grid(True, alpha=0.25, linewidth=0.6)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlim(*x_limits)
        axis.set_ylim(*y_limits)
        axis.set_xlabel("local x coordinate (m)")
    axes[0].set_ylabel("local y coordinate (m)")
    axes[0].legend(loc="lower left", frameon=False)
    fig.tight_layout()
    save(fig, output_dir, "figure_12_uav_gv_trajectories")


def run(dataset: ExperimentDataset, outputs: OutputPaths, generate_figures: bool) -> FeatureResult:
    """Reproduce the separate closed-loop communication-mode comparison."""
    trials = dataset.closed_loop_mode_trials()
    summary = summarize_modes(trials)
    export_table(summary, "table_VI_closed_loop_mode_summary", outputs.tables)
    figures: list[int] = []
    if generate_figures:
        plot_trajectories(dataset.closed_loop_route(), trials, outputs.figures)
        plot_errors(trials, outputs.figures)
        figures = [12, 13]
    return FeatureResult(
        name="closed_loop",
        tables=["table_VI_closed_loop_mode_summary"],
        figures=figures,
        details={"modes": list(MODES), "metric_scope": "active UAV samples only"},
    )
