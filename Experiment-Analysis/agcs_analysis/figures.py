from __future__ import annotations

import math
import os
from pathlib import Path

from .config import PROJECT_DIR

os.environ.setdefault(
    "MPLCONFIGDIR", str(PROJECT_DIR / ".cache" / "matplotlib")
)
os.environ.setdefault("XDG_CACHE_HOME", str(PROJECT_DIR / ".cache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .metrics import wrap_degrees
from .parsers import ControllerLog, deduplicate_state, parse_uav_geo_input
from .yaw_comparison import YawComparisonResults


COLORS = {
    "uav": "#0072B2",
    "ugv": "#D55E00",
    "raw": "#009E73",
    "filtered": "#E69F00",
    "error": "#CC79A7",
    "dark": "#222222",
}


def configure_plots() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "axes.unicode_minus": False,
            "axes.linewidth": 1.1,
            "font.size": 9,
        }
    )


def save(fig, output_dir: Path, stem: str) -> None:
    fig.savefig(output_dir / f"{stem}.png", dpi=300, bbox_inches="tight")
    fig.savefig(output_dir / f"{stem}.pdf", dpi=600, bbox_inches="tight")
    plt.close(fig)


def task_markers(log: ControllerLog) -> list[tuple[float, str, str, str]]:
    markers: list[tuple[float, str, str, str]] = []
    origin = log.origin_wall or log.first_wall
    if log.takeoff_wall:
        markers.append(
            (
                (log.takeoff_wall - origin).total_seconds(),
                "Takeoff",
                "#CC79A7",
                "-.",
            )
        )
    if not log.tasks.empty:
        markers.append(
            (
                float(log.tasks.iloc[0]["mission_wall_s"]),
                "Task start",
                "#009E73",
                "--",
            )
        )
    if not log.task_ends.empty:
        markers.append(
            (
                float(log.task_ends.iloc[0]["mission_wall_s"]),
                "Task end",
                "#D55E00",
                "--",
            )
        )
    return markers


def figure_5(
    log: ControllerLog, uav_log_path: Path, output_dir: Path
) -> None:
    uav = parse_uav_geo_input(uav_log_path)
    if uav.empty:
        uav = log.geo_uav.copy()
    ugv = log.geo_ugv.copy()
    if uav.empty or ugv.empty:
        raise ValueError("Figure 5 requires UAV and UGV geodetic payloads")

    def local_xy(data: pd.DataFrame, lat0: float, lon0: float):
        earth_radius = 6_378_137.0
        x = (
            np.deg2rad(data["longitude_deg"].to_numpy() - lon0)
            * earth_radius
            * math.cos(math.radians(lat0))
        )
        y = (
            np.deg2rad(data["latitude_deg"].to_numpy() - lat0)
            * earth_radius
        )
        return x, y

    lat0 = float(
        pd.concat([uav["latitude_deg"], ugv["latitude_deg"]]).mean()
    )
    lon0 = float(
        pd.concat([uav["longitude_deg"], ugv["longitude_deg"]]).mean()
    )
    ux, uy = local_xy(uav, lat0, lon0)
    gx, gy = local_xy(ugv, lat0, lon0)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot(ux, uy, color=COLORS["uav"], linewidth=1.5, label="UAV path")
    ax.plot(gx, gy, color=COLORS["ugv"], linewidth=1.5, label="GV path")
    ax.scatter(
        ux[0],
        uy[0],
        marker="^",
        color=COLORS["uav"],
        edgecolor="black",
        s=55,
        label="UAV start",
        zorder=4,
    )
    ax.scatter(
        gx[0],
        gy[0],
        marker="^",
        color=COLORS["ugv"],
        edgecolor="black",
        s=55,
        label="GV start",
        zorder=4,
    )
    ax.scatter(
        ux[-1],
        uy[-1],
        marker="X",
        color=COLORS["uav"],
        edgecolor="black",
        s=55,
        label="UAV end",
        zorder=4,
    )
    ax.scatter(
        gx[-1],
        gy[-1],
        marker="X",
        color=COLORS["ugv"],
        edgecolor="black",
        s=55,
        label="GV end",
        zorder=4,
    )
    ax.set_xlabel("East displacement (m)")
    ax.set_ylabel("North displacement (m)")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.2)
    ax.legend(ncol=2, frameon=False, fontsize=8)
    fig.tight_layout()
    save(fig, output_dir, "figure_05_trajectory")


def figure_6(log: ControllerLog, output_dir: Path) -> None:
    uav = deduplicate_state(log.realtime_uav)
    ugv = deduplicate_state(log.realtime_ugv)
    if uav.empty or ugv.empty:
        raise ValueError("Figure 6 requires realtime UAV and UGV states")
    fig, axes = plt.subplots(4, 1, figsize=(6.2, 5.2), sharex=True)
    for axis, column, label in zip(
        axes, ("x_m", "y_m", "z_m", "yaw"), ("X (m)", "Y (m)", "Z (m)", "Yaw")
    ):
        axis.plot(
            uav["state_time_s"],
            uav[column],
            color=COLORS["uav"],
            linewidth=1.1,
            label="UAV",
        )
        axis.plot(
            ugv["state_time_s"],
            ugv[column],
            color=COLORS["ugv"],
            linewidth=1.1,
            label="GV",
        )
        axis.set_ylabel(label)
        for value, _, color, style in task_markers(log):
            axis.axvline(value, color=color, linestyle=style, linewidth=0.9)
    handles = [
        plt.Line2D([], [], color=color, linestyle=style, label=label)
        for _, label, color, style in task_markers(log)
    ]
    handles.extend(
        [
            plt.Line2D([], [], color=COLORS["uav"], label="UAV"),
            plt.Line2D([], [], color=COLORS["ugv"], label="GV"),
        ]
    )
    axes[0].legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.0),
        ncol=len(handles),
        frameon=False,
        fontsize=8,
    )
    axes[-1].set_xlabel("Time (s)")
    fig.tight_layout()
    save(fig, output_dir, "figure_06_state_timeseries")


def figure_7(log: ControllerLog, output_dir: Path) -> None:
    raw = deduplicate_state(log.realtime_ugv)
    filtered = log.positions.copy()
    if raw.empty or filtered.empty:
        raise ValueError("Figure 7 requires raw and controller heading records")
    fig, ax = plt.subplots(figsize=(6.2, 2.1))
    ax.plot(
        raw["state_time_s"],
        np.rad2deg(raw["yaw"]),
        color=COLORS["raw"],
        linestyle="--",
        linewidth=1.0,
        alpha=0.8,
        label="Raw GV yaw",
    )
    ax.plot(
        filtered["mission_wall_s"],
        filtered["ugv_yaw_deg"],
        color=COLORS["filtered"],
        linewidth=1.1,
        label="Filtered GV yaw",
    )
    ax.plot(
        filtered["mission_wall_s"],
        filtered["uav_yaw_deg"],
        color=COLORS["uav"],
        linewidth=1.1,
        label="UAV yaw",
    )
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Yaw (deg)")
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.0),
        ncol=3,
        frameon=False,
    )
    fig.tight_layout()
    save(fig, output_dir, "figure_07_yaw_tracking")


def figure_8(log: ControllerLog, output_dir: Path) -> pd.DataFrame:
    delta = log.deltas.copy()
    positions = log.positions.copy()
    if delta.empty or positions.empty:
        raise ValueError("Figure 8 requires delta and heading records")
    positions["yaw_error_deg"] = wrap_degrees(
        positions["uav_yaw_deg"] - positions["ugv_yaw_deg"]
    )
    fig, axes = plt.subplots(4, 1, figsize=(6.2, 5.2), sharex=True)
    for axis, column, label, color in zip(
        axes[:3],
        ("delta_x_m", "delta_y_m", "delta_z_m"),
        ("X error (m)", "Y error (m)", "Z error (m)"),
        (COLORS["uav"], COLORS["filtered"], COLORS["raw"]),
    ):
        axis.plot(
            delta["mission_wall_s"],
            delta[column],
            color=color,
            linewidth=1.0,
        )
        axis.set_ylabel(label)
    axes[3].plot(
        positions["mission_wall_s"],
        positions["yaw_error_deg"],
        color=COLORS["error"],
        linewidth=1.0,
    )
    axes[3].set_ylabel("Yaw error (deg)")
    axes[3].set_xlabel("Time (s)")
    for axis in axes:
        for value, label, color, style in task_markers(log)[-2:]:
            axis.axvline(
                value, color=color, linestyle=style, linewidth=0.9, label=label
            )
    handles, labels = axes[0].get_legend_handles_labels()
    axes[0].legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.0),
        ncol=2,
        frameon=False,
    )
    fig.tight_layout()
    save(fig, output_dir, "figure_08_tracking_errors")
    return delta[
        [
            "wall_time",
            "mission_wall_s",
            "delta_x_m",
            "delta_y_m",
            "delta_z_m",
        ]
    ]


def communication_panel(
    axis_yaw, axis_pos, log: ControllerLog, cellular_label: str
) -> None:
    remote_yaw = deduplicate_state(log.remote_yaw)
    remote_pos = deduplicate_state(log.remote_pos)
    lora = deduplicate_state(log.lora)
    axis_yaw.scatter(
        remote_yaw["state_time_s"],
        np.rad2deg(remote_yaw["yaw_rad"]),
        s=3,
        color=COLORS["filtered"],
        label=f"{cellular_label} update",
    )
    axis_yaw.scatter(
        lora["state_time_s"],
        -lora["yaw_deg_packet"],
        s=3,
        color=COLORS["uav"],
        label="LoRa",
    )
    axis_pos.scatter(
        remote_pos["y_m"],
        remote_pos["x_m"],
        s=3,
        color=COLORS["filtered"],
        label=f"{cellular_label} update",
    )
    axis_pos.scatter(
        lora["y_m"],
        lora["x_m"],
        s=3,
        color=COLORS["uav"],
        label="LoRa",
    )
    axis_yaw.set_xlabel("Time (s)")
    axis_yaw.set_ylabel("Yaw (deg)")
    axis_pos.set_xlabel("Y coordinate (m)")
    axis_pos.set_ylabel("X coordinate (m)")


def figure_9(
    log_4g: ControllerLog, log_5g: ControllerLog, output_dir: Path
) -> None:
    fig, axes = plt.subplots(1, 4, figsize=(10.0, 2.8))
    communication_panel(axes[0], axes[1], log_4g, "4G")
    communication_panel(axes[2], axes[3], log_5g, "5G")
    for axis in axes:
        axis.tick_params(labelsize=8)
    for pair, center, label in (
        (axes[:2], 0.25, "(a) 4G with LoRa fallback"),
        (axes[2:], 0.75, "(b) 5G with LoRa fallback"),
    ):
        handles, labels = [], []
        for axis in pair:
            for handle, text in zip(*axis.get_legend_handles_labels()):
                if text not in labels:
                    handles.append(handle)
                    labels.append(text)
        fig.legend(
            handles,
            labels,
            loc="upper center",
            bbox_to_anchor=(center, 1.0),
            ncol=len(labels),
            frameon=False,
            fontsize=8,
        )
        fig.text(center, 0.01, label, ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.06, 1, 0.9))
    save(fig, output_dir, "figure_09_dual_mode_streams")


def figure_9_from_updates(data: pd.DataFrame, output_dir: Path) -> None:
    """Render Figure 9 from controller-accepted communication updates.

    In particular, LoRa points are successful controller fallback updates,
    rather than every LoRa packet received by the radio.
    """
    fig, axes = plt.subplots(1, 4, figsize=(10.0, 3.5))
    marker_size = 30
    label_font = 16
    tick_font = 16
    legend_font = 16

    for mode, pair in (("4G", axes[:2]), ("5G", axes[2:])):
        mode_data = data[data["cellular_mode"] == mode]
        yaw = mode_data[mode_data["record_type"] == "yaw"]
        position = mode_data[mode_data["record_type"] == "position"]
        for source, color, label in (
            ("cellular", COLORS["filtered"], f"{mode} update"),
            ("LoRa", COLORS["uav"], "LoRa"),
        ):
            yaw_source = yaw[yaw["source"] == source]
            pair[0].scatter(
                yaw_source["state_time_s"],
                yaw_source["yaw_deg"],
                label=label,
                color=color,
                s=marker_size,
            )
            position_source = position[position["source"] == source]
            pair[1].scatter(
                position_source["y_m"],
                position_source["x_m"],
                label=label,
                color=color,
                s=marker_size,
            )
        pair[0].set_xlabel("Time (s)", fontsize=label_font)
        pair[0].set_ylabel("Yaw (deg)", fontsize=label_font)
        pair[1].set_xlabel("Y coordinate (m)", fontsize=label_font)
        pair[1].set_ylabel("X coordinate (m)", fontsize=label_font)
        for axis in pair:
            axis.tick_params(axis="both", labelsize=tick_font)
            for spine in axis.spines.values():
                spine.set_linewidth(2.0)

    for pair, center, label in (
        (axes[:2], 0.25, "(a) 4G with LoRa fallback"),
        (axes[2:], 0.75, "(b) 5G with LoRa fallback"),
    ):
        handles: list[object] = []
        labels: list[str] = []
        for axis in pair:
            axis_handles, axis_labels = axis.get_legend_handles_labels()
            for handle, text in zip(axis_handles, axis_labels):
                if text not in labels:
                    handles.append(handle)
                    labels.append(text)
        fig.legend(
            handles,
            labels,
            loc="upper center",
            bbox_to_anchor=(center, 0.98),
            ncol=len(labels),
            frameon=False,
            fontsize=legend_font,
        )
        fig.text(center, 0.02, label, ha="center", fontsize=16)

    fig.tight_layout(rect=(0, 0.06, 1, 0.90))
    save(fig, output_dir, "figure_09_dual_mode_streams")


def mark_long_gaps(data: pd.DataFrame, threshold_s: float = 1.0):
    result = data.sort_values("state_time_s", kind="stable").copy()
    result["gap_s"] = result["state_time_s"].diff()
    result["long_gap"] = result["gap_s"] > threshold_s
    return result


def figure_10(log: ControllerLog, output_dir: Path) -> pd.DataFrame:
    remote = mark_long_gaps(deduplicate_state(log.remote_pos))
    lora = mark_long_gaps(deduplicate_state(log.lora))
    fig, axes = plt.subplots(1, 2, figsize=(6.4, 3.0))
    axes[0].scatter(
        remote["y_m"],
        remote["x_m"],
        s=5,
        marker="o",
        color=COLORS["uav"],
        label="5G data",
    )
    loss = remote[remote["long_gap"]]
    axes[0].scatter(
        loss["y_m"],
        loss["x_m"],
        s=20,
        marker="^",
        facecolors="none",
        edgecolors="black",
        label="5G loss",
    )
    axes[1].scatter(
        lora["y_m"],
        lora["x_m"],
        s=5,
        marker="s",
        color=COLORS["ugv"],
        label="LoRa data",
    )
    loss = lora[lora["long_gap"]]
    axes[1].scatter(
        loss["y_m"],
        loss["x_m"],
        s=20,
        marker="D",
        facecolors="none",
        edgecolors="black",
        label="LoRa loss",
    )
    for axis, label in zip(axes, ("(a) 5G", "(b) LoRa")):
        axis.set_xlabel(f"Y coordinate (m)\n{label}")
        axis.set_ylabel("X coordinate (m)")
        axis.set_xlim(-100, 100)
    handles, labels = [], []
    for axis in axes:
        for handle, text in zip(*axis.get_legend_handles_labels()):
            if text not in labels:
                handles.append(handle)
                labels.append(text)
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.0),
        ncol=4,
        frameon=False,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    save(fig, output_dir, "figure_10_single_link_gaps")
    remote_out = remote.assign(source="5G")
    lora_out = lora.assign(source="LoRa")
    return pd.concat([remote_out, lora_out], ignore_index=True)


def figure_10_from_streams(
    cellular: pd.DataFrame,
    lora: pd.DataFrame,
    output_dir: Path,
    gap_threshold_s: float = 1.0,
) -> pd.DataFrame:
    """Render Figure 10 from the full single-link position streams."""
    streams = [
        mark_long_gaps(cellular, threshold_s=gap_threshold_s).assign(
            source="5G"
        ),
        mark_long_gaps(lora, threshold_s=gap_threshold_s).assign(
            source="LoRa"
        ),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(6.0, 3.0))
    for axis, stream, source, marker, loss_marker, color, panel in zip(
        axes,
        streams,
        ("5G", "LoRa"),
        ("o", "s"),
        ("^", "D"),
        (COLORS["uav"], COLORS["ugv"]),
        ("(a) 5G", "(b) LoRa"),
    ):
        axis.scatter(
            stream["y_m"],
            stream["x_m"],
            s=30,
            marker=marker,
            color=color,
            label=f"{source} data",
        )
        losses = stream[stream["long_gap"]]
        axis.scatter(
            losses["y_m"],
            losses["x_m"],
            s=48,
            marker=loss_marker,
            facecolors="none",
            edgecolors="black",
            linewidths=1.2,
            label=f"{source} loss",
        )
        axis.set_xlabel(f"Y coordinate (m)\n{panel}")
        axis.set_ylabel("X coordinate (m)")
        axis.set_xlim(-100, 100)
        for spine in axis.spines.values():
            spine.set_linewidth(2.0)
    handles: list[object] = []
    labels: list[str] = []
    for axis in axes:
        axis_handles, axis_labels = axis.get_legend_handles_labels()
        for handle, text in zip(axis_handles, axis_labels):
            if text not in labels:
                handles.append(handle)
                labels.append(text)
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.99),
        ncol=4,
        frameon=False,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    save(fig, output_dir, "figure_10_single_link_gaps")
    return pd.concat(streams, ignore_index=True)


def figure_10_aligned(
    data: pd.DataFrame,
    output_dir: Path,
    gap_threshold_s: float = 0.3,
) -> pd.DataFrame:
    """Render Figure 10 from the aligned 5G/LoRa position stream."""
    required = {
        "ugv_5g_time",
        "ugv_5g_x",
        "ugv_5g_y",
        "ugv_lora_time",
        "ugv_lora_x",
        "ugv_lora_y",
    }
    missing = required - set(data.columns)
    if missing:
        raise ValueError(
            "Figure 10 requires aligned position columns: "
            + ", ".join(sorted(missing))
        )

    streams = []
    for source, prefix in (("5G", "ugv_5g"), ("LoRa", "ugv_lora")):
        stream = data[
            [f"{prefix}_time", f"{prefix}_x", f"{prefix}_y"]
        ].rename(
            columns={
                f"{prefix}_time": "state_time_s",
                f"{prefix}_x": "x_m",
                f"{prefix}_y": "y_m",
            }
        )
        stream = (
            stream.dropna()
            .drop_duplicates("state_time_s", keep="last")
            .sort_values("state_time_s", kind="stable")
        )
        streams.append(
            mark_long_gaps(stream, threshold_s=gap_threshold_s).assign(
                source=source
            )
        )

    fig, axes = plt.subplots(1, 2, figsize=(6.4, 3.0))
    for axis, stream, source, marker, color, panel in zip(
        axes,
        streams,
        ("5G", "LoRa"),
        ("o", "s"),
        (COLORS["uav"], COLORS["ugv"]),
        ("(a) 5G", "(b) LoRa"),
    ):
        axis.scatter(
            stream["y_m"], stream["x_m"], s=5, marker=marker,
            color=color, label=f"{source} data",
        )
        losses = stream[stream["long_gap"]]
        axis.scatter(
            losses["y_m"], losses["x_m"], s=20, marker="^",
            facecolors="none", edgecolors="black", label=f"{source} loss",
        )
        axis.set_xlabel(f"Y coordinate (m)\n{panel}")
        axis.set_ylabel("X coordinate (m)")
        axis.set_xlim(-100, 100)
    handles, labels = [], []
    for axis in axes:
        for handle, text in zip(*axis.get_legend_handles_labels()):
            if text not in labels:
                handles.append(handle)
                labels.append(text)
    fig.legend(
        handles, labels, loc="upper center", bbox_to_anchor=(0.5, 1.0),
        ncol=4, frameon=False,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    save(fig, output_dir, "figure_10_single_link_gaps")
    return pd.concat(streams, ignore_index=True)


def reconstruct_communication_errors(
    log: ControllerLog,
    leading_distance_m: float,
    timeout_s: float = 0.3,
) -> pd.DataFrame:
    uav = deduplicate_state(log.realtime_uav)[
        ["state_time_s", "x_m", "y_m"]
    ].rename(columns={"x_m": "uav_x_m", "y_m": "uav_y_m"})
    remote_pos = deduplicate_state(log.remote_pos)[
        ["state_time_s", "x_m", "y_m"]
    ].rename(
        columns={
            "state_time_s": "remote_pos_time_s",
            "x_m": "remote_x_m",
            "y_m": "remote_y_m",
        }
    )
    remote_yaw = deduplicate_state(log.remote_yaw)[
        ["state_time_s", "yaw_rad"]
    ].rename(
        columns={
            "state_time_s": "remote_yaw_time_s",
            "yaw_rad": "remote_yaw_rad",
        }
    )
    lora = deduplicate_state(log.lora)[
        ["state_time_s", "x_m", "y_m", "yaw_deg_packet"]
    ].rename(
        columns={
            "state_time_s": "lora_time_s",
            "x_m": "lora_x_m",
            "y_m": "lora_y_m",
        }
    )
    result = pd.merge_asof(
        uav.sort_values("state_time_s", kind="stable"),
        remote_pos.sort_values("remote_pos_time_s", kind="stable"),
        left_on="state_time_s",
        right_on="remote_pos_time_s",
        direction="backward",
    )
    result = pd.merge_asof(
        result.sort_values("state_time_s", kind="stable"),
        remote_yaw.sort_values("remote_yaw_time_s", kind="stable"),
        left_on="state_time_s",
        right_on="remote_yaw_time_s",
        direction="backward",
    )
    result = pd.merge_asof(
        result.sort_values("state_time_s", kind="stable"),
        lora.sort_values("lora_time_s", kind="stable"),
        left_on="state_time_s",
        right_on="lora_time_s",
        direction="backward",
    )
    result = result.dropna(
        subset=[
            "remote_pos_time_s",
            "remote_yaw_time_s",
            "remote_x_m",
            "remote_y_m",
            "remote_yaw_rad",
            "lora_time_s",
            "lora_x_m",
            "lora_y_m",
            "yaw_deg_packet",
        ]
    )
    result["lora_yaw_rad"] = np.deg2rad(-result["yaw_deg_packet"])
    result["remote_state_time_s"] = result[
        ["remote_pos_time_s", "remote_yaw_time_s"]
    ].min(axis=1)
    result["dual_source"] = np.where(
        (
            result["state_time_s"] - result["remote_state_time_s"]
            > timeout_s
        )
        & (result["lora_time_s"] > result["remote_state_time_s"]),
        "lora",
        "cellular",
    )
    dual_uses_lora = result["dual_source"].eq("lora")
    result["dual_x_m"] = result["remote_x_m"].where(
        ~dual_uses_lora, result["lora_x_m"]
    )
    result["dual_y_m"] = result["remote_y_m"].where(
        ~dual_uses_lora, result["lora_y_m"]
    )
    result["dual_yaw_rad"] = result["remote_yaw_rad"].where(
        ~dual_uses_lora, result["lora_yaw_rad"]
    )
    result["dual_state_time_s"] = result["remote_state_time_s"].where(
        ~dual_uses_lora, result["lora_time_s"]
    )
    result["x_des_5g_m"] = (
        result["remote_x_m"]
        + leading_distance_m * np.cos(result["remote_yaw_rad"])
    )
    result["y_des_5g_m"] = (
        result["remote_y_m"]
        + leading_distance_m * np.sin(result["remote_yaw_rad"])
    )
    result["x_des_lora_m"] = (
        result["lora_x_m"]
        + leading_distance_m * np.cos(result["lora_yaw_rad"])
    )
    result["y_des_lora_m"] = (
        result["lora_y_m"]
        + leading_distance_m * np.sin(result["lora_yaw_rad"])
    )
    result["x_des_dual_m"] = (
        result["dual_x_m"]
        + leading_distance_m * np.cos(result["dual_yaw_rad"])
    )
    result["y_des_dual_m"] = (
        result["dual_y_m"]
        + leading_distance_m * np.sin(result["dual_yaw_rad"])
    )
    result["error_x_5g_m"] = result["x_des_5g_m"] - result["uav_x_m"]
    result["error_y_5g_m"] = result["y_des_5g_m"] - result["uav_y_m"]
    result["error_x_lora_m"] = (
        result["x_des_lora_m"] - result["uav_x_m"]
    )
    result["error_y_lora_m"] = (
        result["y_des_lora_m"] - result["uav_y_m"]
    )
    result["error_x_dual_m"] = (
        result["x_des_dual_m"] - result["uav_x_m"]
    )
    result["error_y_dual_m"] = (
        result["y_des_dual_m"] - result["uav_y_m"]
    )
    return result.sort_values("state_time_s", kind="stable").reset_index(drop=True)


def figure_11(
    log: ControllerLog,
    output_dir: Path,
    leading_distance_m: float,
    timeout_s: float = 0.3,
) -> pd.DataFrame:
    data = reconstruct_communication_errors(
        log, leading_distance_m, timeout_s
    )
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 4.0), sharex=True)
    labels = [
        ("5g", "5G-only error", COLORS["uav"]),
        ("lora", "LoRa-only error", COLORS["ugv"]),
        ("dual", "Proposed dual-mode error", COLORS["raw"]),
    ]
    for axis, coordinate in zip(axes, ("x", "y")):
        for mode, label, color in labels:
            axis.plot(
                data["state_time_s"],
                data[f"error_{coordinate}_{mode}_m"],
                label=label,
                color=color,
                linewidth=1.0,
            )
        axis.set_ylabel(f"{coordinate.upper()} error (m)")
        axis.set_xlim(100, 540)
        axis.set_ylim(-10, 10)
    axes[-1].set_xlabel("Time (s)")
    handles, labels_text = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels_text,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.0),
        ncol=3,
        frameon=False,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    save(fig, output_dir, "figure_11_communication_errors")
    return data


def figure_11_aligned(
    data: pd.DataFrame,
    output_dir: Path,
    timeout_s: float = 0.3,
) -> pd.DataFrame:
    """Render Figure 11 from the released aligned position-error columns."""
    required = {
        "time",
        "err_x_5g",
        "err_y_5g",
        "err_x_lora",
        "err_y_lora",
        "dt_5g",
        "ugv_5g_time",
        "ugv_lora_time",
    }
    missing = required - set(data.columns)
    if missing:
        raise ValueError(
            "Figure 11 requires aligned error columns: "
            + ", ".join(sorted(missing))
        )
    result = data.copy()
    use_lora = (
        (result["dt_5g"] > timeout_s)
        & (result["ugv_lora_time"] > result["ugv_5g_time"])
    )
    result["error_x_dual_m"] = result["err_x_5g"].where(
        ~use_lora, result["err_x_lora"]
    )
    result["error_y_dual_m"] = result["err_y_5g"].where(
        ~use_lora, result["err_y_lora"]
    )
    result = result.rename(
        columns={
            "err_x_5g": "error_x_5g_m",
            "err_y_5g": "error_y_5g_m",
            "err_x_lora": "error_x_lora_m",
            "err_y_lora": "error_y_lora_m",
        }
    )
    result["dual_source"] = np.where(use_lora, "lora", "cellular")

    fig, axes = plt.subplots(2, 1, figsize=(7.0, 4.0), sharex=True)
    labels = [
        ("5g", "5G-only error", COLORS["uav"]),
        ("lora", "LoRa-only error", COLORS["ugv"]),
        ("dual", "Proposed dual-mode error", COLORS["raw"]),
    ]
    for axis, coordinate in zip(axes, ("x", "y")):
        for mode, label, color in labels:
            axis.plot(
                result["time"], result[f"error_{coordinate}_{mode}_m"],
                label=label, color=color, linewidth=1.0,
            )
        axis.set_ylabel(f"{coordinate.upper()} error (m)")
        axis.set_xlim(float(result["time"].min()), float(result["time"].max()))
        axis.set_ylim(-10, 10)
    axes[-1].set_xlabel("Time (s)")
    handles, labels_text = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels_text, loc="upper center", bbox_to_anchor=(0.5, 1.0),
        ncol=3, frameon=False,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    save(fig, output_dir, "figure_11_communication_errors")
    return result


def figure_11_from_reconstruction(
    data: pd.DataFrame,
    output_dir: Path,
    window_s: tuple[float, float] = (100.0, 540.0),
) -> pd.DataFrame:
    """Render Figure 11 from the corrected forward-lead reconstruction."""
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 4.0), sharex=True)
    labels = [
        ("5g", "5G-only error", COLORS["uav"], 3.5, 2),
        ("lora", "LoRa-only error", COLORS["ugv"], 3.5, 1),
        ("proposed", "Proposed method error", COLORS["raw"], 2.5, 5),
    ]
    for axis, coordinate, title in zip(
        axes,
        ("x", "y"),
        (
            "X-axis tracking error comparison",
            "Y-axis tracking error comparison",
        ),
    ):
        for mode, label, color, width, zorder in labels:
            axis.plot(
                data["time"],
                data[f"err_{coordinate}_{mode}"],
                label=label,
                color=color,
                linewidth=width,
                zorder=zorder,
            )
        axis.set_ylabel(f"{coordinate.upper()} error (m)")
        axis.set_title(title)
        axis.set_xlim(*window_s)
        axis.set_ylim(-10, 10)
        for spine in axis.spines.values():
            spine.set_linewidth(2.0)
    axes[-1].set_xlabel("Time (s)")
    handles, labels_text = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels_text,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.02),
        ncol=3,
        frameon=False,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    save(fig, output_dir, "figure_11_communication_errors")
    return data


def figure_12(results: YawComparisonResults, output_dir: Path) -> None:
    """Plot the four-trial yaw comparison used by the revised paper.

    The RTK course is an independent reference shown only where the vehicle is
    moving fast enough to define a valid course angle.  It is not supplied to
    any of the filters.  Draw it and the proposed AKF above the baselines so
    that their close overlap does not hide the two curves central to the
    comparison.
    """
    fig, axes = plt.subplots(2, 2, figsize=(12.0, 4.4))
    axes = axes.ravel()
    styles = [
        (
            "raw_yaw_deg",
            "Raw GV",
            COLORS["dark"],
            ":",
            2.0,
            0.65,
            1,
        ),
        (
            "reference_yaw_deg",
            "RTK course ref.",
            COLORS["filtered"],
            "--",
            1.8,
            1.0,
            6,
        ),
        ("EKF_yaw_deg", "EKF", COLORS["ugv"], "-", 1.1, 1.0, 2),
        ("EKF-AR_yaw_deg", "EKF-AR", COLORS["raw"], "-", 1.1, 1.0, 3),
        (
            "Huber-based KF_yaw_deg",
            "Huber KF",
            COLORS["error"],
            "-",
            1.1,
            1.0,
            4,
        ),
        (
            "AKF (proposed)_yaw_deg",
            "AKF",
            COLORS["uav"],
            "-",
            1.8,
            1.0,
            8,
        ),
    ]
    plotted_axes = []
    for index, (_, data) in enumerate(list(results.series.items())[:4]):
        axis = axes[index]
        plotted_axes.append(axis)
        for column, label, color, style, width, alpha, zorder in styles:
            axis.plot(
                data["time"],
                data[column],
                label=label,
                color=color,
                linestyle=style,
                linewidth=width,
                alpha=alpha,
                zorder=zorder,
            )
        axis.set_xlabel("Time (s)")
        axis.set_ylabel("Yaw (deg)")
        axis.tick_params(axis="both", labelsize=10)
        axis.text(
            -0.08,
            1.02,
            f"({chr(ord('a') + index)})",
            transform=axis.transAxes,
            fontsize=14,
            fontweight="bold",
            va="bottom",
            ha="left",
        )

    for axis in axes[len(plotted_axes):]:
        fig.delaxes(axis)

    handles: list[object] = []
    labels: list[str] = []
    for axis in plotted_axes:
        axis_handles, axis_labels = axis.get_legend_handles_labels()
        for handle, label in zip(axis_handles, axis_labels):
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
    save(fig, output_dir, "figure_12_heading_filters")


def generate_all_figures(
    representative: ControllerLog,
    representative_uav_path: Path,
    communication_4g: ControllerLog,
    communication_5g: ControllerLog,
    heading_results: HeadingResults,
    output_dir: Path,
    leading_distance_m: float,
) -> dict[str, pd.DataFrame]:
    configure_plots()
    figure_5(representative, representative_uav_path, output_dir)
    figure_6(representative, output_dir)
    figure_7(representative, output_dir)
    figure_8_audit = figure_8(representative, output_dir)
    figure_9(communication_4g, communication_5g, output_dir)
    figure_10_audit = figure_10(communication_5g, output_dir)
    figure_11_audit = figure_11(
        communication_5g,
        output_dir,
        leading_distance_m,
    )
    figure_12(heading_results, output_dir)
    return {
        "figure_08_error_series": figure_8_audit,
        "figure_10_gap_markers": figure_10_audit,
        "figure_11_error_series": figure_11_audit,
    }
