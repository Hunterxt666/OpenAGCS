"""Reproducible leader-only platoon escort simulation for Figure 15.

The simulation uses one leader GV, six follower GVs, and one UAV.  The UAV
receives only the delayed leader state, causally extrapolates that state with
the transmitted velocity, and follows a 10 m forward escort reference.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .figures import plt, save


@dataclass(frozen=True)
class PlatoonConfig:
    """Vehicle-platoon dynamics and numerical integration settings."""

    time_step_s: float = 0.02
    duration_s: float = 20.0
    time_headway_s: float = 1.0
    standstill_gap_m: float = 1.0
    vehicle_length_m: float = 4.0
    linear_gain: float = 7.0
    direction_gain: float = 3.0
    longitudinal_acceleration_min_mps2: float = -7.0
    longitudinal_acceleration_max_mps2: float = 5.0
    lateral_acceleration_min_mps2: float = -4.0
    lateral_acceleration_max_mps2: float = 4.0
    disturbed_vehicle_index: int = 3
    disturbance_mps2: float = 0.5


@dataclass(frozen=True)
class EscortConfig:
    """Leader-state relay and UAV escort settings used in the paper."""

    relay_delay_s: float = 0.2
    packet_loss_rate: float = 0.10
    random_seed: int = 70061
    transmission_period_s: float = 0.1
    desired_offset_m: float = 10.0
    uav_position_gain: float = 2.8
    wind_memory: float = 0.96
    wind_noise_std_mps: float = 0.018
    # Rounded median per-axis high-frequency residual from the logged UAV
    # positions after removing a 2 s centered local quadratic trend.
    uav_position_noise_std_m: float = 0.02
    freshness_threshold_s: float = 0.3


@dataclass(frozen=True)
class EscortResult:
    heading_rad: np.ndarray
    packet_received: np.ndarray
    packet_dropped: np.ndarray
    received_source_index: np.ndarray
    state_age_s: np.ndarray
    ideal_reference_xy_m: np.ndarray
    relayed_reference_xy_m: np.ndarray
    uav_xy_m: np.ndarray
    escort_error_m: np.ndarray


def initial_platoon_state() -> np.ndarray:
    """Return the paper's seven-vehicle initial state as ``[x, y, vx, vy]``."""

    return np.array(
        [
            [310.0, 0.0, 14.0, 0.0],
            [292.0, -1.0, 16.0, 0.5],
            [278.0, 1.0, 16.0, -0.5],
            [264.0, -1.0, 14.0, 0.5],
            [249.0, 1.0, 15.0, -0.5],
            [235.0, -1.0, 14.0, 0.5],
            [220.0, 1.0, 16.0, -0.5],
        ],
        dtype=float,
    )


def leader_acceleration(time_s: float) -> np.ndarray:
    """Piecewise longitudinal/lateral acceleration of the leader GV."""

    if 0.0 <= time_s < 5.0:
        return np.array([1.8, 3.0])
    if 10.0 <= time_s < 15.0:
        return np.array([-2.0, -3.0])
    return np.zeros(2)


def state_derivative(
    time_s: float,
    flat_state: np.ndarray,
    config: PlatoonConfig,
) -> np.ndarray:
    """Evaluate the continuous longitudinal/lateral platoon dynamics."""

    state = flat_state.reshape(-1, 4)
    derivative = np.zeros_like(state)
    derivative[0] = np.array(
        [state[0, 2], state[0, 3], *leader_acceleration(time_s)]
    )

    feedback_gain = np.array(
        [[-1.0, 0.0, -2.0, 0.0], [0.0, -1.0, 0.0, -2.0]]
    )
    disturbance_sign = (-1.0) ** np.floor(time_s)
    disturbance = np.full(2, config.disturbance_mps2 * disturbance_sign)

    for vehicle_index in range(1, len(state)):
        desired_spacing = (
            (state[vehicle_index, 2] - state[vehicle_index - 1, 2])
            * config.time_headway_s
            + config.standstill_gap_m
            + config.vehicle_length_m
        )
        relative_state = np.array(
            [
                state[vehicle_index, 0]
                + desired_spacing
                - state[vehicle_index - 1, 0],
                state[vehicle_index, 1] - state[vehicle_index - 1, 1],
                state[vehicle_index, 2] - state[vehicle_index - 1, 2],
                state[vehicle_index, 3] - state[vehicle_index - 1, 3],
            ]
        )
        raw_control = feedback_gain @ relative_state
        norm = np.linalg.norm(raw_control)
        direction = raw_control / norm if norm > 1e-12 else np.zeros(2)
        acceleration = (
            config.linear_gain * raw_control + config.direction_gain * direction
        )
        if vehicle_index == config.disturbed_vehicle_index:
            acceleration += disturbance
        acceleration[0] = np.clip(
            acceleration[0],
            config.longitudinal_acceleration_min_mps2,
            config.longitudinal_acceleration_max_mps2,
        )
        acceleration[1] = np.clip(
            acceleration[1],
            config.lateral_acceleration_min_mps2,
            config.lateral_acceleration_max_mps2,
        )
        derivative[vehicle_index] = np.array(
            [
                state[vehicle_index, 2],
                state[vehicle_index, 3],
                acceleration[0],
                acceleration[1],
            ]
        )

    return derivative.reshape(-1)


def simulate_platoon(
    config: PlatoonConfig = PlatoonConfig(),
) -> tuple[np.ndarray, np.ndarray]:
    """Integrate the seven-vehicle platoon with fourth-order Runge--Kutta."""

    if config.time_step_s <= 0.0 or config.duration_s <= 0.0:
        raise ValueError("simulation time step and duration must be positive")

    initial_state = initial_platoon_state().reshape(-1)
    time_s = np.arange(
        0.0,
        config.duration_s + config.time_step_s / 2.0,
        config.time_step_s,
    )
    flat_states = np.zeros((len(time_s), len(initial_state)))
    flat_states[0] = initial_state

    for index in range(1, len(time_s)):
        step_start = time_s[index - 1]
        state = flat_states[index - 1]
        step = config.time_step_s
        k1 = state_derivative(step_start, state, config)
        k2 = state_derivative(
            step_start + step / 2.0, state + step * k1 / 2.0, config
        )
        k3 = state_derivative(
            step_start + step / 2.0, state + step * k2 / 2.0, config
        )
        k4 = state_derivative(step_start + step, state + step * k3, config)
        flat_states[index] = state + step * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0

    return time_s, flat_states.reshape(len(time_s), -1, 4)


def _integer_steps(interval_s: float, time_step_s: float, name: str) -> int:
    steps = int(round(interval_s / time_step_s))
    if steps <= 0 or not np.isclose(steps * time_step_s, interval_s):
        raise ValueError(f"{name} must be a positive multiple of the time step")
    return steps


def simulate_uav_escort(
    time_s: np.ndarray,
    platoon_states: np.ndarray,
    config: EscortConfig = EscortConfig(),
) -> EscortResult:
    """Simulate delayed/lossy leader-state relay and onboard UAV escort."""

    if len(time_s) < 2 or len(platoon_states) != len(time_s):
        raise ValueError("time and platoon state arrays must have equal length")
    if not 0.0 <= config.packet_loss_rate < 1.0:
        raise ValueError("packet loss rate must be in [0, 1)")

    rng = np.random.default_rng(config.random_seed)
    leader = platoon_states[:, 0, :]
    time_step_s = float(time_s[1] - time_s[0])
    transmission_steps = _integer_steps(
        config.transmission_period_s, time_step_s, "transmission period"
    )
    delay_steps = _integer_steps(
        config.relay_delay_s, time_step_s, "relay delay"
    )

    heading_rad = np.unwrap(np.arctan2(leader[:, 3], leader[:, 2]))
    packet_received = np.zeros(len(time_s), dtype=bool)
    packet_dropped = np.zeros(len(time_s), dtype=bool)
    received_source_index = np.zeros(len(time_s), dtype=int)
    last_received_source = 0

    for receive_index in range(delay_steps, len(time_s), transmission_steps):
        source_index = receive_index - delay_steps
        if rng.random() > config.packet_loss_rate:
            last_received_source = source_index
            packet_received[receive_index] = True
        else:
            packet_dropped[receive_index] = True
        received_source_index[receive_index:] = last_received_source

    state_age_s = time_s - time_s[received_source_index]
    received_leader = leader[received_source_index]
    extrapolated_leader_xy = (
        received_leader[:, 0:2]
        + received_leader[:, 2:4] * state_age_s[:, None]
    )
    received_heading = heading_rad[received_source_index]
    relayed_reference_xy_m = extrapolated_leader_xy + np.column_stack(
        [
            config.desired_offset_m * np.cos(received_heading),
            config.desired_offset_m * np.sin(received_heading),
        ]
    )
    ideal_reference_xy_m = leader[:, 0:2] + np.column_stack(
        [
            config.desired_offset_m * np.cos(heading_rad),
            config.desired_offset_m * np.sin(heading_rad),
        ]
    )

    uav_xy_m = np.zeros_like(relayed_reference_xy_m)
    uav_xy_m[0] = relayed_reference_xy_m[0] + np.array([-1.0, 0.5])
    wind_mps = np.zeros(2)
    for index in range(1, len(time_s)):
        wind_mps = config.wind_memory * wind_mps + rng.normal(
            0.0, config.wind_noise_std_mps, 2
        )
        reference_velocity = (
            relayed_reference_xy_m[index]
            - relayed_reference_xy_m[index - 1]
        ) / time_step_s
        command_velocity = reference_velocity + config.uav_position_gain * (
            relayed_reference_xy_m[index - 1] - uav_xy_m[index - 1]
        )
        uav_xy_m[index] = (
            uav_xy_m[index - 1]
            + time_step_s * command_velocity
            + time_step_s * wind_mps
        )

    uav_xy_m += rng.normal(
        0.0, config.uav_position_noise_std_m, uav_xy_m.shape
    )
    escort_error_m = np.linalg.norm(
        uav_xy_m - ideal_reference_xy_m, axis=1
    )
    return EscortResult(
        heading_rad=heading_rad,
        packet_received=packet_received,
        packet_dropped=packet_dropped,
        received_source_index=received_source_index,
        state_age_s=state_age_s,
        ideal_reference_xy_m=ideal_reference_xy_m,
        relayed_reference_xy_m=relayed_reference_xy_m,
        uav_xy_m=uav_xy_m,
        escort_error_m=escort_error_m,
    )


def summarize_escort(result: EscortResult) -> dict[str, float]:
    """Return the six metrics reported in paper Table XIV."""

    return {
        "mean_state_age_s": float(np.mean(result.state_age_s)),
        "p95_state_age_s": float(np.percentile(result.state_age_s, 95)),
        "maximum_state_age_s": float(np.max(result.state_age_s)),
        "uav_escort_rmse_m": float(
            np.sqrt(np.mean(result.escort_error_m**2))
        ),
        "uav_escort_p95_error_m": float(
            np.percentile(result.escort_error_m, 95)
        ),
        "uav_escort_maximum_error_m": float(np.max(result.escort_error_m)),
    }


def table_xiv(metrics: dict[str, float]) -> pd.DataFrame:
    """Format the simulation summary as the two-column manuscript table."""

    return pd.DataFrame(
        [
            ("Mean state age", f"{metrics['mean_state_age_s']:.3f} s"),
            ("95% state age", f"{metrics['p95_state_age_s']:.3f} s"),
            ("Maximum state age", f"{metrics['maximum_state_age_s']:.3f} s"),
            ("UAV escort RMSE", f"{metrics['uav_escort_rmse_m']:.3f} m"),
            (
                "UAV escort 95% error",
                f"{metrics['uav_escort_p95_error_m']:.3f} m",
            ),
            (
                "UAV escort maximum error",
                f"{metrics['uav_escort_maximum_error_m']:.3f} m",
            ),
        ],
        columns=["metric", "value"],
    )


def simulation_series(
    time_s: np.ndarray,
    platoon_states: np.ndarray,
    result: EscortResult,
) -> pd.DataFrame:
    """Build the machine-readable audit series underlying Figure 15."""

    data: dict[str, np.ndarray] = {
        "time_s": time_s,
        "leader_x_m": platoon_states[:, 0, 0],
        "leader_y_m": platoon_states[:, 0, 1],
        "desired_uav_x_m": result.ideal_reference_xy_m[:, 0],
        "desired_uav_y_m": result.ideal_reference_xy_m[:, 1],
        "relayed_reference_x_m": result.relayed_reference_xy_m[:, 0],
        "relayed_reference_y_m": result.relayed_reference_xy_m[:, 1],
        "uav_x_m": result.uav_xy_m[:, 0],
        "uav_y_m": result.uav_xy_m[:, 1],
        "state_age_s": result.state_age_s,
        "escort_error_m": result.escort_error_m,
        "packet_received": result.packet_received,
        "packet_dropped": result.packet_dropped,
        "received_source_time_s": time_s[result.received_source_index],
    }
    for vehicle_index in range(1, platoon_states.shape[1]):
        data[f"follower_{vehicle_index}_x_m"] = platoon_states[
            :, vehicle_index, 0
        ]
        data[f"follower_{vehicle_index}_y_m"] = platoon_states[
            :, vehicle_index, 1
        ]
    return pd.DataFrame(data)


def figure_15(
    time_s: np.ndarray,
    platoon_states: np.ndarray,
    result: EscortResult,
    output_dir: Path,
    freshness_threshold_s: float,
) -> None:
    """Render and save the three-panel platoon escort figure."""

    sample = slice(None, None, 5)
    colors = {
        "leader": "#0072B2",
        "follower": "#999999",
        "uav": "#D55E00",
        "reference": "#009E73",
        "age": "#CC79A7",
        "error": "#E69F00",
    }
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.35))

    trajectory_axis = axes[0]
    for vehicle_index in range(1, platoon_states.shape[1]):
        trajectory_axis.plot(
            platoon_states[sample, vehicle_index, 0],
            platoon_states[sample, vehicle_index, 1],
            color=colors["follower"],
            linewidth=0.85,
            alpha=0.72,
            label="follower GVs" if vehicle_index == 1 else "_nolegend_",
            zorder=1,
        )
    trajectory_axis.plot(
        platoon_states[sample, 0, 0],
        platoon_states[sample, 0, 1],
        color=colors["leader"],
        linewidth=1.7,
        label="leader GV",
        zorder=3,
    )
    trajectory_axis.plot(
        result.uav_xy_m[sample, 0],
        result.uav_xy_m[sample, 1],
        color=colors["uav"],
        linewidth=1.45,
        alpha=0.88,
        label="UAV",
        zorder=4,
    )
    trajectory_axis.plot(
        result.ideal_reference_xy_m[sample, 0],
        result.ideal_reference_xy_m[sample, 1],
        color=colors["reference"],
        linewidth=2.2,
        linestyle=(0, (4, 2)),
        marker="^",
        markevery=12,
        markersize=3.0,
        markerfacecolor="white",
        markeredgecolor=colors["reference"],
        markeredgewidth=0.7,
        label="desired UAV",
        zorder=6,
    )
    trajectory_axis.set_xlabel("Longitudinal position (m)")
    trajectory_axis.set_ylabel("Lateral position (m)")
    trajectory_axis.grid(True, alpha=0.25)
    trajectory_axis.legend(
        loc="best",
        fontsize=5.6,
        frameon=True,
        framealpha=0.82,
        borderpad=0.25,
        handlelength=1.6,
    )
    trajectory_axis.set_title("(a)")

    age_axis = axes[1]
    age_axis.plot(time_s, result.state_age_s, color=colors["age"], linewidth=1.3)
    dropped_time_s = time_s[result.packet_dropped]
    age_axis.scatter(
        dropped_time_s,
        np.full_like(dropped_time_s, 0.34),
        s=6,
        color="#666666",
        marker="x",
        linewidths=0.6,
        label="dropped update",
    )
    age_axis.axhline(
        freshness_threshold_s,
        color="#000000",
        linewidth=0.8,
        linestyle=":",
        label=f"{freshness_threshold_s:.1f} s threshold",
    )
    age_axis.set_ylim(0.0, 0.5)
    age_axis.set_xlabel("Time (s)")
    age_axis.set_ylabel("State age (s)")
    age_axis.grid(True, alpha=0.25)
    age_axis.legend(loc="upper right", fontsize=6, frameon=False)
    age_axis.set_title("(b)")

    error_axis = axes[2]
    error_axis.plot(
        time_s, result.escort_error_m, color=colors["error"], linewidth=1.3
    )
    error_axis.set_xlabel("Time (s)")
    error_axis.set_ylabel("Escort error (m)")
    error_axis.grid(True, alpha=0.25)
    error_axis.set_title("(c)")

    fig.tight_layout(w_pad=1.2)
    save(fig, output_dir, "figure_15_platoon_uav_delay_loss")


def write_simulation_metadata(
    path: Path,
    platoon_config: PlatoonConfig,
    escort_config: EscortConfig,
    metrics: dict[str, float],
) -> None:
    """Persist parameters and full-precision metrics for auditability."""

    payload = {
        "platoon_config": asdict(platoon_config),
        "escort_config": asdict(escort_config),
        "metrics": metrics,
        "relative_air_ground_state_load": 1.0 / 7.0,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
