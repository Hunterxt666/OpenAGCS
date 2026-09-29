"""Main onboard control loop for the paper's UAV follow mission.

This entrypoint waits until the middleware publishes a valid origin, then keeps
the controller alive and switches between follow-mode and return/land according
to the remote depart flag maintained by the communication framework.
"""

import argparse
import math
import os
import time

from Tools.RequestTools import get_origin_pos
import Tools.LogUtil as log
from VehicleAgent.DroneAgent import DroneAgent


def positive_float(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return value


def nonnegative_float(value):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return value


def positive_integer(value):
    try:
        value = int(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the AGCS UAV controller")
    parser.add_argument(
        "--remote-url",
        default=os.environ.get("AGCS_REMOTE_URL"),
        help="remote communication API base URL (or AGCS_REMOTE_URL)",
    )
    parser.add_argument(
        "--local-url",
        default=os.environ.get(
            "AGCS_LOCAL_URL",
            "http://127.0.0.1:26969",
        ),
        help="local onboard communication API base URL",
    )
    parser.add_argument(
        "--kp-xy",
        type=nonnegative_float,
        default=os.environ.get("AGCS_PD_KP_XY", "0.8"),
        help="horizontal proportional gain (default: 0.8)",
    )
    parser.add_argument(
        "--kd-xy",
        type=nonnegative_float,
        default=os.environ.get("AGCS_PD_KD_XY", "0.2"),
        help="horizontal derivative gain (default: 0.2)",
    )
    parser.add_argument(
        "--kp-z",
        type=nonnegative_float,
        default=os.environ.get("AGCS_PD_KP_Z", "0.8"),
        help="vertical proportional gain (default: 0.8)",
    )
    parser.add_argument(
        "--kd-z",
        type=nonnegative_float,
        default=os.environ.get("AGCS_PD_KD_Z", "0.15"),
        help="vertical derivative gain (default: 0.15)",
    )
    parser.add_argument(
        "--derivative-filter-tau",
        type=nonnegative_float,
        default=os.environ.get("AGCS_PD_FILTER_TAU", "0.2"),
        help="derivative low-pass time constant in seconds (default: 0.2)",
    )
    parser.add_argument(
        "--clock-skew-tolerance",
        type=nonnegative_float,
        default=os.environ.get("AGCS_CLOCK_SKEW_TOLERANCE", "0"),
        help="explicit causal timestamp allowance in seconds (default: 0)",
    )
    parser.add_argument(
        "--state-freshness-timeout",
        type=positive_float,
        default=os.environ.get("AGCS_STATE_FRESHNESS_TIMEOUT", "0.3"),
        help="telemetry freshness timeout in seconds (default: 0.3)",
    )
    parser.add_argument(
        "--stale-state-hold-timeout",
        type=positive_float,
        default=os.environ.get("AGCS_STALE_STATE_HOLD_TIMEOUT", "2.0"),
        help=(
            "maximum GV reference hold time before safe hover in seconds "
            "(default: 2.0)"
        ),
    )
    parser.add_argument(
        "--link-heartbeat-timeout",
        type=positive_float,
        default=os.environ.get("AGCS_LINK_HEARTBEAT_TIMEOUT"),
        help="link heartbeat timeout (default: state freshness timeout)",
    )
    parser.add_argument(
        "--link-failure-threshold",
        type=positive_integer,
        default=os.environ.get("AGCS_LINK_FAILURE_THRESHOLD", "3"),
        help="consecutive delivery failures before failover (default: 3)",
    )
    parser.add_argument(
        "--cellular-recovery-window",
        type=positive_float,
        default=os.environ.get("AGCS_CELLULAR_RECOVERY_WINDOW", "1.0"),
        help="continuous cellular health before recovery in seconds (default: 1)",
    )
    parser.add_argument(
        "--takeoff-timeout",
        type=positive_float,
        default=os.environ.get("AGCS_TAKEOFF_TIMEOUT", "20"),
        help="takeoff confirmation timeout in seconds (default: 20)",
    )
    parser.add_argument(
        "--climb-timeout",
        type=positive_float,
        default=os.environ.get("AGCS_CLIMB_TIMEOUT", "90"),
        help="mission-altitude timeout in seconds (default: 90)",
    )
    parser.add_argument(
        "--positioning-timeout",
        type=positive_float,
        default=os.environ.get("AGCS_POSITIONING_TIMEOUT", "90"),
        help="initial guiding-pose timeout in seconds (default: 90)",
    )
    parser.add_argument(
        "--preflight-timeout",
        type=positive_float,
        default=os.environ.get("AGCS_PREFLIGHT_TIMEOUT", "10"),
        help="state and dual-link confirmation timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--preflight-stable-window",
        type=positive_float,
        default=os.environ.get("AGCS_PREFLIGHT_STABLE_WINDOW", "0.5"),
        help="continuous preflight readiness window in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--return-timeout",
        type=positive_float,
        default=os.environ.get("AGCS_RETURN_TIMEOUT", "90"),
        help="return-to-GV timeout in seconds (default: 90)",
    )
    parser.add_argument(
        "--landing-timeout",
        type=positive_float,
        default=os.environ.get("AGCS_LANDING_TIMEOUT", "60"),
        help="touchdown confirmation timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--takeoff-stable-window",
        type=positive_float,
        default=os.environ.get("AGCS_TAKEOFF_STABLE_WINDOW", "0.5"),
        help="continuous lift-off stability window (default: 0.5)",
    )
    args = parser.parse_args(argv)
    if not args.remote_url:
        parser.error("--remote-url or AGCS_REMOTE_URL is required")
    if args.stale_state_hold_timeout < args.state_freshness_timeout:
        parser.error(
            "--stale-state-hold-timeout must be no smaller than "
            "--state-freshness-timeout"
        )
    return args


if __name__ == '__main__':
    args = parse_args()
    url_remote = args.remote_url.rstrip("/")
    url_local = args.local_url.rstrip("/")
    while get_origin_pos(url_local) is None:
        log.warn("[Main Process] Origin not set, continue waiting for origin")
        time.sleep(3)
    log.success("[Main Process] Origin set successfully, entering main loop")
    drone = DroneAgent(
        url_remote=url_remote,
        url_local=url_local,
        kp_xy=args.kp_xy,
        kd_xy=args.kd_xy,
        kp_z=args.kp_z,
        kd_z=args.kd_z,
        derivative_filter_tau=args.derivative_filter_tau,
        clock_skew_tolerance=args.clock_skew_tolerance,
        state_freshness_timeout=args.state_freshness_timeout,
        stale_state_hold_timeout=args.stale_state_hold_timeout,
        link_heartbeat_timeout=args.link_heartbeat_timeout,
        link_failure_threshold=args.link_failure_threshold,
        cellular_recovery_window=args.cellular_recovery_window,
        takeoff_timeout=args.takeoff_timeout,
        climb_timeout=args.climb_timeout,
        positioning_timeout=args.positioning_timeout,
        preflight_timeout=args.preflight_timeout,
        preflight_stable_window=args.preflight_stable_window,
        return_timeout=args.return_timeout,
        landing_timeout=args.landing_timeout,
        takeoff_stable_window=args.takeoff_stable_window,
    )
    while True:
        log.success("[Main Process] Heartbeat...")
        if drone.emergency_stop_active:
            log.error(
                "[Main Process] Emergency stop active; mission transitions "
                "are suspended"
            )
        elif drone.remote_depart_order is True and not drone.depart_flag:
            log.success("[Main Process] Start follow task")
            if not drone.depart_and_start_follow():
                log.error("[Main Process] Follow mission did not become active")
        elif drone.remote_depart_order is False and drone.depart_flag:
            log.success("[Main Process] Stop follow task")
            if not drone.return_to_car_and_land():
                log.error(
                    "[Main Process] Return/landing remains incomplete; "
                    "the controller is holding a safe state"
                )
        time.sleep(2)
