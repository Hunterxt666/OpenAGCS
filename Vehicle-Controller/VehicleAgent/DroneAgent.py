"""UAV follow-control agent used in the onboard computation pipeline."""

import math
import threading
import time

from Tools.GvStateSupervisor import GvStateSupervisor
from Tools.RequestTools import (
    check_depart,
    check_emergency_stop,
    get_cellular_gv_state,
    get_follow_config,
    get_height,
    get_lora_gv_state,
    get_lora_link_status,
    get_mission_id,
    get_pos,
    set_mission_state,
    set_uav_control_input,
    set_uav_control_input_cmd,
)
import Tools.LogUtil as log


class DroneAgent:
    """Maintain mission state and generate velocity/yaw commands for the UAV."""

    DEFAULT_HEIGHT = 30.0
    DEFAULT_GUIDING_RANGE = 10.0

    PHASE_IDLE = "IDLE"
    PHASE_PREPARING = "PREPARING"
    PHASE_TAKEOFF = "TAKEOFF"
    PHASE_POSITIONING = "POSITIONING"
    PHASE_ESCORT = "ESCORT"
    PHASE_RETURNING = "RETURNING"
    PHASE_DESCENDING = "DESCENDING"
    PHASE_LANDING = "LANDING"
    PHASE_FAULT = "FAULT"

    def __init__(
        self,
        url_local,
        url_remote,
        max_xy_speed=10.0,
        max_angel=180.0,
        max_z_speed=5.0,
        state_freshness_timeout=0.3,
        stale_state_hold_timeout=2.0,
        clock_skew_tolerance=0.0,
        link_heartbeat_timeout=None,
        link_failure_threshold=3,
        cellular_recovery_window=1.0,
        kp_xy=0.8,
        kd_xy=0.2,
        kp_z=0.8,
        kd_z=0.15,
        derivative_filter_tau=0.2,
        max_xy_error_rate=20.0,
        max_z_error_rate=10.0,
        takeoff_timeout=20.0,
        climb_timeout=90.0,
        positioning_timeout=90.0,
        preflight_timeout=10.0,
        return_timeout=90.0,
        landing_timeout=60.0,
        takeoff_stable_window=0.5,
        preflight_stable_window=0.5,
        pose_stable_window=1.0,
        landing_stable_window=0.5,
        position_tolerance=0.75,
        height_tolerance=0.5,
        velocity_tolerance=0.3,
        landing_approach_height=2.0,
        landing_ground_threshold=0.3,
        landing_confirm_height=0.7,
        require_both_preflight_links=True,
        start_background_workers=True,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        self.max_angel = self._positive_finite(max_angel, "max_angel")
        self.max_xy_speed = self._positive_finite(
            max_xy_speed, "max_xy_speed"
        )
        self.max_z_speed = self._positive_finite(max_z_speed, "max_z_speed")
        self.state_freshness_timeout = self._positive_finite(
            state_freshness_timeout, "state_freshness_timeout"
        )
        self.stale_state_hold_timeout = self._positive_finite(
            stale_state_hold_timeout, "stale_state_hold_timeout"
        )
        if self.stale_state_hold_timeout < self.state_freshness_timeout:
            raise ValueError(
                "stale_state_hold_timeout must not be smaller than "
                "state_freshness_timeout"
            )
        self.clock_skew_tolerance = self._nonnegative_finite(
            clock_skew_tolerance, "clock_skew_tolerance"
        )
        if self.clock_skew_tolerance > self.state_freshness_timeout:
            raise ValueError(
                "clock_skew_tolerance must not exceed "
                "state_freshness_timeout"
            )
        if link_heartbeat_timeout is None:
            link_heartbeat_timeout = self.state_freshness_timeout
        self.link_heartbeat_timeout = self._positive_finite(
            link_heartbeat_timeout, "link_heartbeat_timeout"
        )
        if (
            isinstance(link_failure_threshold, bool)
            or int(link_failure_threshold) != link_failure_threshold
            or link_failure_threshold <= 0
        ):
            raise ValueError("link_failure_threshold must be a positive integer")
        self.link_failure_threshold = int(link_failure_threshold)
        self.cellular_recovery_window = self._positive_finite(
            cellular_recovery_window, "cellular_recovery_window"
        )

        self.kp_xy = self._nonnegative_finite(kp_xy, "kp_xy")
        self.kd_xy = self._nonnegative_finite(kd_xy, "kd_xy")
        self.kp_z = self._nonnegative_finite(kp_z, "kp_z")
        self.kd_z = self._nonnegative_finite(kd_z, "kd_z")
        self.derivative_filter_tau = self._nonnegative_finite(
            derivative_filter_tau, "derivative_filter_tau"
        )
        self.max_xy_error_rate = self._positive_finite(
            max_xy_error_rate, "max_xy_error_rate"
        )
        self.max_z_error_rate = self._positive_finite(
            max_z_error_rate, "max_z_error_rate"
        )
        self._pd_reset_interval = max(
            1.0,
            4.0 * self.derivative_filter_tau,
            2.0 * self.state_freshness_timeout,
        )

        self.takeoff_timeout = self._positive_finite(
            takeoff_timeout, "takeoff_timeout"
        )
        self.climb_timeout = self._positive_finite(
            climb_timeout, "climb_timeout"
        )
        self.positioning_timeout = self._positive_finite(
            positioning_timeout, "positioning_timeout"
        )
        self.preflight_timeout = self._positive_finite(
            preflight_timeout, "preflight_timeout"
        )
        self.return_timeout = self._positive_finite(
            return_timeout, "return_timeout"
        )
        self.landing_timeout = self._positive_finite(
            landing_timeout, "landing_timeout"
        )
        self.takeoff_stable_window = self._positive_finite(
            takeoff_stable_window, "takeoff_stable_window"
        )
        self.preflight_stable_window = self._positive_finite(
            preflight_stable_window, "preflight_stable_window"
        )
        self.pose_stable_window = self._positive_finite(
            pose_stable_window, "pose_stable_window"
        )
        self.landing_stable_window = self._positive_finite(
            landing_stable_window, "landing_stable_window"
        )
        self.position_tolerance = self._positive_finite(
            position_tolerance, "position_tolerance"
        )
        self.height_tolerance = self._positive_finite(
            height_tolerance, "height_tolerance"
        )
        self.velocity_tolerance = self._positive_finite(
            velocity_tolerance, "velocity_tolerance"
        )
        self.landing_approach_height = self._positive_finite(
            landing_approach_height, "landing_approach_height"
        )
        self.landing_ground_threshold = self._nonnegative_finite(
            landing_ground_threshold, "landing_ground_threshold"
        )
        self.landing_confirm_height = self._positive_finite(
            landing_confirm_height, "landing_confirm_height"
        )
        if self.landing_ground_threshold >= self.landing_confirm_height:
            raise ValueError(
                "landing_ground_threshold must be below "
                "landing_confirm_height"
            )
        if not isinstance(require_both_preflight_links, bool):
            raise ValueError("require_both_preflight_links must be boolean")
        self.require_both_preflight_links = require_both_preflight_links

        self.url_local = url_local
        self.url_remote = url_remote
        self._clock = clock
        self._sleep = sleep

        # UAV position and height are sampled independently. Their source and
        # receive timestamps are retained so repeated HTTP reads cannot make a
        # frozen sensor value appear fresh.
        self.pos = [None] * 3
        self.pre_pos = [None] * 3
        self.yaw = 0.0
        self.t = 0.0
        self.pre_t = -1.0
        self.vx = 0.0
        self.vy = 0.0
        self.vz = 0.0
        self._uav_state_lock = threading.Lock()
        self._uav_state_snapshot = None
        self._height_state_snapshot = None

        self.ugv_pos = [None] * 2
        self.ugv_yaw = None
        self.gv_state_supervisor = GvStateSupervisor(
            self.state_freshness_timeout,
            stale_state_hold_timeout=self.stale_state_hold_timeout,
            clock_skew_tolerance=self.clock_skew_tolerance,
            link_heartbeat_timeout=self.link_heartbeat_timeout,
            link_failure_threshold=self.link_failure_threshold,
            cellular_recovery_window=self.cellular_recovery_window,
            clock=self._clock,
        )
        self._gv_source_log_lock = threading.Lock()
        self._last_consumed_gv_source = None
        self.is_gv_state_stale = False
        self._holding_stale_gv_reference = False
        self.hover_confirmed = False
        self.last_hover_attempt = float("-inf")

        self.cmd = [
            "TAKEOFF",
            "COFIRMLAND",
            "LAND",
            "OFFCONTROL",
            "HOVER",
        ]
        self.ctrl_seq = [0.0] * 4
        self._ctrl_lock = threading.Lock()
        self._control_transport_lock = threading.RLock()

        self._pd_lock = threading.Lock()
        self._pd_previous_error = None
        self._pd_filtered_derivative = [0.0, 0.0, 0.0]
        self._pd_previous_time = None

        self.depart_flag = False
        self.departed = False
        self.stop_flag = False
        self.ctrl_process = None
        self._stop_follow_event = threading.Event()
        self.remote_depart_order = None
        self.emergency_stop_active = False
        self._emergency_clear_observed = False
        self.active_mission_id = None
        self.mission_phase = self.PHASE_IDLE
        self._landing_start_height = None
        self._last_published_mission_state = None
        self._last_mission_state_publish_at = float("-inf")
        self._last_attempted_mission_state = None
        self._last_mission_state_attempt_at = float("-inf")

        self.send_speed_thread = self._worker(
            self.set_uav_control_to_local, "uav-control-sender"
        )
        self.send_uav_get_pos_from_local_thread = self._worker(
            self.uav_get_pos_from_local, "uav-position-poller"
        )
        self.cellular_gv_state_thread = self._worker(
            self.poll_cellular_gv_state, "cellular-gv-poller"
        )
        self.lora_gv_state_thread = self._worker(
            self.poll_lora_gv_state, "lora-gv-poller"
        )
        self.send_uav_get_height_from_local_thread = self._worker(
            self.uav_get_height_from_local, "uav-height-poller"
        )
        self.check_order_thread = self._worker(
            self.check_depart_status, "depart-order-poller"
        )
        self.check_emergency_thread = self._worker(
            self.check_emergency_status, "emergency-stop-poller"
        )
        self.mission_status_thread = self._worker(
            self.publish_mission_status, "mission-status-publisher"
        )

        if start_background_workers:
            for worker in (
                self.send_speed_thread,
                self.send_uav_get_pos_from_local_thread,
                self.cellular_gv_state_thread,
                self.lora_gv_state_thread,
                self.send_uav_get_height_from_local_thread,
                self.check_order_thread,
                self.check_emergency_thread,
                self.mission_status_thread,
            ):
                worker.start()

    @staticmethod
    def _positive_finite(value, name):
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a positive finite value")
        return value

    @staticmethod
    def _nonnegative_finite(value, name):
        value = float(value)
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a nonnegative finite value")
        return value

    @staticmethod
    def _worker(target, name):
        return threading.Thread(target=target, name=name, daemon=True)

    def process_uav_position(self, pos_data, received_at=None):
        """Accept one genuinely new, epoch-matched UAV position sample."""
        try:
            if pos_data["mission_id"] is None:
                raise ValueError("mission_id must not be None")
            mission_id = str(pos_data["mission_id"])
            x = float(pos_data["current_pos"][0])
            y = float(pos_data["current_pos"][1])
            sensed_at = float(pos_data["time"])
            if not all(math.isfinite(value) for value in (x, y, sensed_at)):
                raise ValueError("UAV state values must be finite")
        except (KeyError, IndexError, TypeError, ValueError) as error:
            log.error(f"[DroneAgent] Invalid local UAV state: {error}")
            return False

        if received_at is None:
            received_at = self._clock()
        received_at = float(received_at)
        if not math.isfinite(received_at):
            raise ValueError("received_at must be finite")

        with self._uav_state_lock:
            wrong_mission = (
                self.active_mission_id is not None
                and mission_id != self.active_mission_id
            )
            previous = self._uav_state_snapshot
            cached_or_out_of_order = (
                previous is not None
                and previous["mission_id"] == mission_id
                and sensed_at <= previous["sensed_at"]
            )
            if wrong_mission or cached_or_out_of_order:
                return False

            if previous is None or previous["mission_id"] != mission_id:
                self.pre_pos[0], self.pre_pos[1] = None, None
                self.pre_t = -1.0
                self.vx = 0.0
                self.vy = 0.0
            elif sensed_at > previous["sensed_at"]:
                dt = sensed_at - previous["sensed_at"]
                self.yaw = math.atan2(
                    y - previous["position"][1],
                    x - previous["position"][0],
                )
                self.vx = (x - previous["position"][0]) / dt
                self.vy = (y - previous["position"][1]) / dt

            self.pos[0], self.pos[1] = x, y
            self.t = sensed_at
            self.pre_pos[0], self.pre_pos[1] = x, y
            self.pre_t = sensed_at
            self._uav_state_snapshot = {
                "mission_id": mission_id,
                "position": (x, y),
                "velocity": (self.vx, self.vy),
                "sensed_at": sensed_at,
                "received_at": received_at,
            }
        return True

    def process_uav_height(self, height_data, received_at=None):
        """Accept a new height sample without refreshing duplicate data."""
        try:
            if height_data["mission_id"] is None:
                raise ValueError("mission_id must not be None")
            mission_id = str(height_data["mission_id"])
            height = float(height_data["height"])
            sensed_at = float(height_data["sensed_at"])
            if not all(math.isfinite(value) for value in (height, sensed_at)):
                raise ValueError("height state values must be finite")
        except (KeyError, TypeError, ValueError) as error:
            log.error(f"[DroneAgent] Invalid local UAV height state: {error}")
            return False

        if received_at is None:
            received_at = self._clock()
        received_at = float(received_at)
        if not math.isfinite(received_at):
            raise ValueError("received_at must be finite")

        with self._uav_state_lock:
            if (
                self.active_mission_id is not None
                and mission_id != self.active_mission_id
            ):
                return False
            previous = self._height_state_snapshot
            if (
                previous is not None
                and previous["mission_id"] == mission_id
                and sensed_at <= previous["sensed_at"]
            ):
                return False

            self.pre_pos[2] = self.pos[2]
            if (
                previous is not None
                and previous["mission_id"] == mission_id
            ):
                dt = sensed_at - previous["sensed_at"]
                self.vz = (height - previous["height"]) / dt
            else:
                self.vz = 0.0
            self.pos[2] = height
            self._height_state_snapshot = {
                "mission_id": mission_id,
                "height": height,
                "vertical_speed": self.vz,
                "sensed_at": sensed_at,
                "received_at": received_at,
            }
        return True

    def uav_get_pos_from_local(self):
        while True:
            pos_data = get_pos(self.url_local)
            if pos_data:
                self.process_uav_position(pos_data)
            self._sleep(0.1)

    def uav_get_height_from_local(self):
        while True:
            height_data = get_height(self.url_local)
            if height_data is not None:
                self.process_uav_height(height_data)
            self._sleep(0.1)

    def check_depart_status(self):
        while True:
            order = check_depart(self.url_remote)
            if order is not None:
                self.remote_depart_order = order
            self._sleep(5.0)

    def check_emergency_status(self):
        """Consume both local LoRa and remote cellular emergency channels."""
        while True:
            local_state = check_emergency_stop(self.url_local)
            remote_state = (
                None
                if local_state is True
                else check_emergency_stop(self.url_remote)
            )
            self.update_emergency_stop(local_state, remote_state)
            self._sleep(0.1)

    def update_emergency_stop(self, local_state, remote_state):
        """Latch one process-level hard stop from either communication path."""
        states = (local_state, remote_state)
        if any(state is True for state in states):
            with self._control_transport_lock:
                if not self.emergency_stop_active:
                    self.emergency_stop_active = True
                    self._emergency_clear_observed = False
                    self.stop_flag = True
                    self._stop_follow_event.set()
                    self.reset_pd_controller()
                    if self.mission_phase == self.PHASE_LANDING:
                        log.error(
                            "[DroneAgent] Emergency stop latched during "
                            "automatic landing; joystick commands remain "
                            "disabled"
                        )
                    else:
                        if self.depart_flag or self.departed:
                            self._send_zero_velocity(
                                emergency_override=True
                            )
                            self.set_uav_control_cmd_to_local(
                                "HOVER",
                                emergency_override=True,
                            )
                        self.mission_phase = self.PHASE_FAULT
                        log.error(
                            "[DroneAgent] Emergency stop latched; guidance "
                            "is disabled until Controller and Executor restart"
                        )
            return True

        if all(state is False for state in states):
            with self._control_transport_lock:
                if self.emergency_stop_active:
                    if not self._emergency_clear_observed:
                        log.warn(
                            "[DroneAgent] Emergency source cleared, but the "
                            "hard stop remains latched; inspect the aircraft "
                            "and restart Controller and Executor"
                        )
                        self._emergency_clear_observed = True
                    return True
                return False

        # Unknown communication state never clears a latched emergency.
        return None

    def poll_cellular_gv_state(self):
        while True:
            state = get_cellular_gv_state(self.url_remote)
            if state is None:
                self.gv_state_supervisor.observe_link("cellular", False)
            else:
                # RequestTools has already validated the complete payload.
                # Link health is observed independently from cache admission,
                # which may still reject a duplicate or wrong-mission sample.
                self.gv_state_supervisor.observe_link("cellular", True)
                try:
                    self.gv_state_supervisor.update(
                        source="cellular",
                        mission_id=state["mission_id"],
                        sample_id=state["sample_id"],
                        position=state["position"],
                        yaw_degrees=state["yaw_degrees"],
                        sensed_at=state["sensed_at"],
                        height=state.get("height"),
                        velocity=state.get("velocity"),
                    )
                except (KeyError, TypeError, ValueError) as error:
                    log.error(
                        f"[DroneAgent] Invalid cellular GV state: {error}"
                    )
            self._sleep(0.05)

    def poll_lora_gv_state(self):
        while True:
            link_healthy = get_lora_link_status(
                self.url_local,
                timeout=self.link_heartbeat_timeout,
            )
            self.gv_state_supervisor.observe_link("lora", link_healthy)
            state = get_lora_gv_state(self.url_local)
            if state:
                try:
                    self.gv_state_supervisor.update(
                        source="lora",
                        mission_id=state["mission_id"],
                        sample_id=state["sample_id"],
                        position=state["position"],
                        yaw_degrees=state["yaw_degrees"],
                        sensed_at=state["sensed_at"],
                        height=state.get("height"),
                        velocity=state.get("velocity"),
                    )
                except (KeyError, TypeError, ValueError) as error:
                    log.error(f"[DroneAgent] Invalid LoRa GV state: {error}")
            self._sleep(0.05)

    def publish_mission_status_once(self, now=None):
        """Publish controller-confirmed mission state to the operator API."""
        mission_id = self.active_mission_id
        if mission_id is None:
            return None
        if now is None:
            now = self._clock()
        active_source = (
            None
            if self.mission_phase in {self.PHASE_IDLE, self.PHASE_FAULT}
            else self.gv_state_supervisor.active_source
        )
        status = (
            str(mission_id),
            self.mission_phase,
            active_source,
            bool(self.depart_flag or self.departed),
        )
        if (
            status == self._last_published_mission_state
            and now - self._last_mission_state_publish_at < 1.0
        ):
            return None
        if (
            status == self._last_attempted_mission_state
            and now - self._last_mission_state_attempt_at < 1.0
        ):
            return None
        self._last_attempted_mission_state = status
        self._last_mission_state_attempt_at = now
        sent = set_mission_state(
            self.url_remote,
            mission_id=status[0],
            phase=status[1],
            active_source=status[2],
            airborne=status[3],
        )
        if sent:
            self._last_published_mission_state = status
            self._last_mission_state_publish_at = now
        return sent

    def publish_mission_status(self):
        while True:
            self.publish_mission_status_once()
            self._sleep(0.1)

    def set_uav_control_to_local(self):
        while True:
            with self._control_transport_lock:
                if (
                    self.departed
                    and not self.emergency_stop_active
                    and self.mission_phase != self.PHASE_LANDING
                ):
                    with self._ctrl_lock:
                        command = tuple(self.ctrl_seq)
                    set_uav_control_input(
                        url=self.url_local,
                        vx=command[0],
                        vy=command[1],
                        vz=command[2],
                        yaw=command[3],
                    )
            self._sleep(0.2)

    def set_uav_control_cmd_to_local(
        self,
        cmd,
        emergency_override=False,
    ):
        if cmd not in self.cmd:
            return False
        with self._control_transport_lock:
            if (
                self.emergency_stop_active
                and not emergency_override
                and cmd not in ("COFIRMLAND", "OFFCONTROL")
            ):
                log.error(
                    f"[DroneAgent] Refusing {cmd} after emergency-stop latch"
                )
                return False
            if (
                self.mission_phase == self.PHASE_LANDING
                and cmd not in ("LAND", "COFIRMLAND", "OFFCONTROL")
            ):
                log.error(
                    f"[DroneAgent] Refusing {cmd} during automatic landing"
                )
                return False
            with self._ctrl_lock:
                yaw = self.ctrl_seq[-1]
            self.update_vel_ctrl_seq(0.0, 0.0, 0.0, yaw)
            success = set_uav_control_input_cmd(self.url_local, cmd=cmd)
        if success:
            log.success(f"[DroneAgent] Execute {cmd} successfully")
        else:
            log.error(f"[DroneAgent] Execute {cmd} failed")
        return success

    def _send_zero_velocity(self, emergency_override=False):
        with self._control_transport_lock:
            if self.emergency_stop_active and not emergency_override:
                log.error(
                    "[DroneAgent] Refusing joystick handoff after "
                    "emergency-stop latch"
                )
                return False
            if self.mission_phase == self.PHASE_LANDING:
                log.error(
                    "[DroneAgent] Refusing joystick handoff during automatic "
                    "landing"
                )
                return False
            with self._ctrl_lock:
                yaw = self.ctrl_seq[-1]
            self.update_vel_ctrl_seq(0.0, 0.0, 0.0, yaw)
            return set_uav_control_input(
                self.url_local,
                vx=0.0,
                vy=0.0,
                vz=0.0,
                yaw=yaw,
            )

    def update_vel_ctrl_seq(self, forward, leftward, upward, alpha):
        values = (forward, leftward, upward, alpha)
        try:
            forward, leftward, upward, alpha = (
                float(value) for value in values
            )
        except (TypeError, ValueError):
            raise ValueError("control values must be numeric")
        if not all(
            math.isfinite(value)
            for value in (forward, leftward, upward, alpha)
        ):
            raise ValueError("control values must be finite")

        forward = min(self.max_xy_speed, max(forward, -self.max_xy_speed))
        leftward = min(
            self.max_xy_speed, max(leftward, -self.max_xy_speed)
        )
        upward = min(self.max_z_speed, max(upward, -self.max_z_speed))
        alpha = min(self.max_angel, max(alpha, -self.max_angel))
        with self._ctrl_lock:
            self.ctrl_seq = [forward, leftward, upward, alpha]

    def reset_pd_controller(self):
        """Discard derivative history at mission and safety-mode boundaries."""
        with self._pd_lock:
            self._pd_previous_error = None
            self._pd_filtered_derivative = [0.0, 0.0, 0.0]
            self._pd_previous_time = None

    def compute_pd_velocity(self, error, now=None):
        """Apply Eq. (11) using a filtered finite-difference derivative."""
        if len(error) != 3:
            raise ValueError("error must contain x, y, and z")
        error = tuple(float(value) for value in error)
        if not all(math.isfinite(value) for value in error):
            raise ValueError("error values must be finite")
        if now is None:
            now = self._clock()
        now = float(now)
        if not math.isfinite(now):
            raise ValueError("now must be finite")

        with self._pd_lock:
            derivative = [0.0, 0.0, 0.0]
            if (
                self._pd_previous_error is not None
                and self._pd_previous_time is not None
            ):
                dt = now - self._pd_previous_time
                if 1e-6 < dt <= self._pd_reset_interval:
                    raw = [
                        (error[index] - self._pd_previous_error[index]) / dt
                        for index in range(3)
                    ]
                    raw[0] = min(
                        self.max_xy_error_rate,
                        max(raw[0], -self.max_xy_error_rate),
                    )
                    raw[1] = min(
                        self.max_xy_error_rate,
                        max(raw[1], -self.max_xy_error_rate),
                    )
                    raw[2] = min(
                        self.max_z_error_rate,
                        max(raw[2], -self.max_z_error_rate),
                    )
                    coefficient = (
                        1.0
                        if self.derivative_filter_tau == 0.0
                        else dt / (self.derivative_filter_tau + dt)
                    )
                    derivative = [
                        previous + coefficient * (current - previous)
                        for previous, current in zip(
                            self._pd_filtered_derivative, raw
                        )
                    ]

            self._pd_previous_error = error
            self._pd_filtered_derivative = derivative
            self._pd_previous_time = now

        return (
            self.kp_xy * error[0] + self.kd_xy * derivative[0],
            self.kp_xy * error[1] + self.kd_xy * derivative[1],
            self.kp_z * error[2] + self.kd_z * derivative[2],
        )

    def _current_mission_time(self, now=None, uav_state=None):
        if now is None:
            now = self._clock()
        now = float(now)
        if not math.isfinite(now):
            raise ValueError("now must be finite")
        if uav_state is None:
            with self._uav_state_lock:
                uav_state = (
                    None
                    if self._uav_state_snapshot is None
                    else dict(self._uav_state_snapshot)
                )
                active_mission_id = self.active_mission_id
        else:
            uav_state = dict(uav_state)
            with self._uav_state_lock:
                active_mission_id = self.active_mission_id
        if (
            uav_state is None
            or (
                active_mission_id is not None
                and uav_state["mission_id"] != active_mission_id
            )
        ):
            return None
        receive_age = now - uav_state["received_at"]
        if not 0.0 <= receive_age <= self.state_freshness_timeout:
            return None
        return uav_state["sensed_at"] + receive_age

    def _fresh_height_snapshot(self, now=None):
        if now is None:
            now = self._clock()
        now = float(now)
        if not math.isfinite(now):
            raise ValueError("now must be finite")
        with self._uav_state_lock:
            height_state = (
                None
                if self._height_state_snapshot is None
                else dict(self._height_state_snapshot)
            )
            uav_state = (
                None
                if self._uav_state_snapshot is None
                else dict(self._uav_state_snapshot)
            )
        if (
            height_state is None
            or uav_state is None
            or height_state["mission_id"] != uav_state["mission_id"]
            or not 0.0
            <= now - height_state["received_at"]
            <= self.state_freshness_timeout
        ):
            return None
        current_mission_time = self._current_mission_time(now, uav_state)
        if current_mission_time is None:
            return None
        height_age = current_mission_time - height_state["sensed_at"]
        if not (
            -self.clock_skew_tolerance
            <= height_age
            <= self.state_freshness_timeout
        ):
            return None
        return height_state

    def _reset_gv_source_log(self):
        with self._gv_source_log_lock:
            self._last_consumed_gv_source = None

    def _log_consumed_gv_source(self, gv_state, current_sensed_at):
        """Log the initial selected link and every consumed link transition."""
        source = gv_state["source"]
        sensed_at = float(gv_state["sensed_at"])
        state_age = float(current_sensed_at) - sensed_at
        with self._gv_source_log_lock:
            previous = self._last_consumed_gv_source
            if source == previous:
                return False
            self._last_consumed_gv_source = source
            if previous is None:
                transition = f"selected: {source}"
            else:
                transition = f"switched: {previous} -> {source}"
            log.info(
                "[DroneAgent] GV state mode "
                f"{transition} (sensed_at={sensed_at:.3f}, "
                f"state_age={state_age:.3f} s)"
            )
        return True

    def _guidance_state(self, now=None):
        if now is None:
            now = self._clock()
        with self._uav_state_lock:
            uav_state = (
                None
                if self._uav_state_snapshot is None
                else dict(self._uav_state_snapshot)
            )
            height_state = (
                None
                if self._height_state_snapshot is None
                else dict(self._height_state_snapshot)
            )

        if uav_state is None or height_state is None:
            return None
        if not (
            0.0
            <= now - uav_state["received_at"]
            <= self.state_freshness_timeout
            and 0.0
            <= now - height_state["received_at"]
            <= self.state_freshness_timeout
        ):
            return None

        current_mission_time = self._current_mission_time(now, uav_state)
        if current_mission_time is None:
            return None
        height_age = current_mission_time - height_state["sensed_at"]
        if not (
            -self.clock_skew_tolerance
            <= height_age
            <= self.state_freshness_timeout
        ):
            return None

        gv_state = self.gv_state_supervisor.select(
            now=now,
            current_sensed_at=current_mission_time,
        )
        if gv_state is None:
            return None
        self._log_consumed_gv_source(gv_state, current_mission_time)
        return {
            "uav": uav_state,
            "height": height_state,
            "gv": gv_state,
        }

    @staticmethod
    def _guidance_error(state, height, guiding_range):
        gv_state = state["gv"]
        uav_state = state["uav"]
        yaw = math.radians(gv_state["yaw_degrees"])
        target_x = gv_state["position"][0] + guiding_range * math.cos(yaw)
        target_y = gv_state["position"][1] + guiding_range * math.sin(yaw)
        return (
            target_x - uav_state["position"][0],
            target_y - uav_state["position"][1],
            height - state["height"]["height"],
        )

    def _guidance_metrics(self, height, guiding_range, now=None):
        state = self._guidance_state(now)
        if state is None:
            return None
        error = self._guidance_error(state, height, guiding_range)
        velocity = state["uav"]["velocity"]
        return {
            "state": state,
            "error": error,
            "planar_error": math.hypot(error[0], error[1]),
            "height_error": abs(error[2]),
            "horizontal_speed": math.hypot(velocity[0], velocity[1]),
            "vertical_speed": abs(state["height"]["vertical_speed"]),
        }

    def _pose_is_stable(self, metrics):
        return (
            metrics is not None
            and metrics["planar_error"] <= self.position_tolerance
            and metrics["height_error"] <= self.height_tolerance
            and metrics["horizontal_speed"] <= self.velocity_tolerance
            and metrics["vertical_speed"] <= self.velocity_tolerance
        )

    def _wait_for_guiding_pose(
        self,
        height,
        guiding_range,
        timeout,
        abort_on_stop_order=False,
    ):
        deadline = self._clock() + timeout
        stable_since = None
        while self._clock() < deadline:
            if abort_on_stop_order and self.remote_depart_order is False:
                log.warn("[DroneAgent] Positioning cancelled by operator")
                return False
            if self.emergency_stop_active:
                log.error("[DroneAgent] Positioning aborted by emergency stop")
                return False

            now = self._clock()
            metrics = self._guidance_metrics(height, guiding_range, now)
            if self._pose_is_stable(metrics):
                if stable_since is None:
                    stable_since = now
                elif now - stable_since >= self.pose_stable_window:
                    return True
            else:
                stable_since = None
            self._sleep(0.05)
        return False

    def _wait_for_preflight(self):
        """Confirm fresh same-mission state and initialized transport links."""
        deadline = self._clock() + self.preflight_timeout
        stable_since = None
        while self._clock() < deadline:
            if self.remote_depart_order is False or self.emergency_stop_active:
                return False
            now = self._clock()
            guidance_state = self._guidance_state(now)
            link_health = self.gv_state_supervisor.link_health(now)
            links_ready = (
                all(link_health.values())
                if self.require_both_preflight_links
                else any(link_health.values())
            )
            if guidance_state is not None and links_ready:
                if stable_since is None:
                    stable_since = now
                elif now - stable_since >= self.preflight_stable_window:
                    return True
            else:
                stable_since = None
            self._sleep(0.05)
        return False

    def _complete_guidance_stage(self, height, guiding_range, description):
        """Reach and verify one guarded return/landing guidance target."""
        if not self.start_follow_mission(
            height=height,
            guiding_range=guiding_range,
        ):
            self._command_safe_hover(f"{description} controller did not start")
            self.mission_phase = self.PHASE_FAULT
            return False
        reached = self._wait_for_guiding_pose(
            height=height,
            guiding_range=guiding_range,
            timeout=self.return_timeout,
        )
        if not self.stop_follow_mission():
            self._command_safe_hover(f"{description} controller did not stop")
            self.mission_phase = self.PHASE_FAULT
            return False
        if not reached:
            self._command_safe_hover(
                f"{description} target was not reached before timeout"
            )
            self.mission_phase = self.PHASE_FAULT
            return False
        metrics = self._guidance_metrics(
            height=height,
            guiding_range=guiding_range,
        )
        if not self._pose_is_stable(metrics):
            self._command_safe_hover(
                f"{description} geometry changed during controller handoff"
            )
            self.mission_phase = self.PHASE_FAULT
            return False
        return True

    def _command_safe_hover(self, reason):
        with self._control_transport_lock:
            if self.emergency_stop_active:
                log.error(
                    f"[DroneAgent] {reason}; emergency stop is latched, so no "
                    "new hover command will be issued"
                )
                return False
            self.reset_pd_controller()
            with self._ctrl_lock:
                yaw = self.ctrl_seq[-1]
            self.update_vel_ctrl_seq(0.0, 0.0, 0.0, yaw)
            log.warn(f"[DroneAgent] {reason}; commanding safe hover")
            return self.set_uav_control_cmd_to_local("HOVER")

    def hold_for_stale_state(self, now=None):
        """Command zero velocity and retry HOVER until it is acknowledged."""
        if now is None:
            now = self._clock()
        if not self.is_gv_state_stale:
            log.warn("[DroneAgent] UAV/GV/height state stale; safe hover")
            self.is_gv_state_stale = True
            self.hover_confirmed = False
            self.reset_pd_controller()
        with self._ctrl_lock:
            yaw = self.ctrl_seq[-1]
        self.update_vel_ctrl_seq(0.0, 0.0, 0.0, yaw)
        if (
            not self.hover_confirmed
            and now - self.last_hover_attempt >= 0.2
        ):
            self.last_hover_attempt = now
            self.hover_confirmed = self.set_uav_control_cmd_to_local("HOVER")
        return self.hover_confirmed

    def fly_to_guiding_range(
        self,
        height=DEFAULT_HEIGHT,
        guiding_range=DEFAULT_GUIDING_RANGE,
    ):
        """Continuously track the paper's desired guiding point using PD."""
        while not self._stop_follow_event.is_set():
            now = self._clock()
            state = self._guidance_state(now)
            if state is None:
                self.hold_for_stale_state(now)
                self._sleep(0.05)
                continue

            holding_stale_reference = bool(state["gv"].get("is_stale"))
            if holding_stale_reference and not self._holding_stale_gv_reference:
                log.warn(
                    "[DroneAgent] Holding the latest GV reference during "
                    "temporary state unavailability"
                )
            elif (
                not holding_stale_reference
                and self._holding_stale_gv_reference
                and not self.is_gv_state_stale
            ):
                log.success("[DroneAgent] Fresh GV state restored")
            self._holding_stale_gv_reference = holding_stale_reference

            if self.is_gv_state_stale:
                log.success(
                    "[DroneAgent] Fresh state restored via "
                    f"{state['gv']['source']}"
                )
                self.is_gv_state_stale = False
                self.hover_confirmed = False
                self.reset_pd_controller()

            gv_state = state["gv"]
            self.ugv_pos[0], self.ugv_pos[1] = gv_state["position"]
            self.ugv_yaw = math.radians(gv_state["yaw_degrees"])
            error = self._guidance_error(state, height, guiding_range)
            velocity = self.compute_pd_velocity(error, now=now)
            self.update_vel_ctrl_seq(
                velocity[0],
                velocity[1],
                velocity[2],
                gv_state["yaw_degrees"],
            )
            self._sleep(0.05)

    def start_follow_mission(
        self,
        height=DEFAULT_HEIGHT,
        guiding_range=DEFAULT_GUIDING_RANGE,
    ):
        if self.emergency_stop_active:
            log.error(
                "[DroneAgent] Refusing guidance start during emergency stop"
            )
            return False
        if not self.stop_follow_mission():
            return False
        with self._control_transport_lock:
            if self.emergency_stop_active:
                self.mission_phase = self.PHASE_FAULT
                log.error(
                    "[DroneAgent] Emergency stop arrived before guidance start"
                )
                return False
            self.stop_flag = False
            self._stop_follow_event.clear()
            self.reset_pd_controller()
            self.ctrl_process = threading.Thread(
                target=self.fly_to_guiding_range,
                args=(height, guiding_range),
                name="uav-guidance-controller",
                daemon=True,
            )
            self.ctrl_process.start()
        return True

    def stop_follow_mission(self, join_timeout=2.0):
        process = self.ctrl_process
        if process is None:
            self.stop_flag = True
            self._stop_follow_event.set()
            self.reset_pd_controller()
            return True

        self.stop_flag = True
        self._stop_follow_event.set()
        process.join(timeout=join_timeout)
        if process.is_alive():
            log.error("[DroneAgent] Guidance thread did not stop in time")
            return False

        self.ctrl_process = None
        with self._ctrl_lock:
            yaw = self.ctrl_seq[-1]
        self.update_vel_ctrl_seq(0.0, 0.0, 0.0, yaw)
        self.reset_pd_controller()
        return True

    def _wait_for_takeoff(self, baseline_height):
        deadline = self._clock() + self.takeoff_timeout
        stable_since = None
        while self._clock() < deadline:
            if self.remote_depart_order is False:
                return False
            if self.emergency_stop_active:
                return False
            state = self._fresh_height_snapshot()
            if state is not None:
                if baseline_height is None:
                    baseline_height = state["height"]
                lift_off_height = (
                    state["height"] >= 0.5
                    or state["height"] - baseline_height >= 0.3
                )
                if (
                    lift_off_height
                    and abs(state["vertical_speed"])
                    <= self.velocity_tolerance
                ):
                    if stable_since is None:
                        stable_since = self._clock()
                    elif (
                        self._clock() - stable_since
                        >= self.takeoff_stable_window
                    ):
                        return True
                else:
                    stable_since = None
            else:
                stable_since = None
            self._sleep(0.05)
        return False

    def _climb_to_height(self, height, speed):
        deadline = self._clock() + self.climb_timeout
        stable_since = None
        self.reset_pd_controller()
        while self._clock() < deadline:
            if self.remote_depart_order is False:
                return False
            if self.emergency_stop_active:
                return False
            now = self._clock()
            state = self._fresh_height_snapshot(now)
            if state is None:
                self.hold_for_stale_state(now)
                stable_since = None
                self._sleep(0.05)
                continue

            if self.is_gv_state_stale:
                self.is_gv_state_stale = False
                self.hover_confirmed = False
                self.reset_pd_controller()
            error = height - state["height"]
            velocity = self.compute_pd_velocity((0.0, 0.0, error), now)
            upward = min(speed, max(velocity[2], -speed))
            self.update_vel_ctrl_seq(0.0, 0.0, upward, 0.0)

            if (
                abs(error) <= self.height_tolerance
                and abs(state["vertical_speed"]) <= self.velocity_tolerance
            ):
                if stable_since is None:
                    stable_since = now
                elif now - stable_since >= self.pose_stable_window:
                    return True
            else:
                stable_since = None
            self._sleep(0.05)
        return False

    def send_depart(self, speed=3.0, height=DEFAULT_HEIGHT):
        """Take off and reach the configured mission altitude."""
        if self.emergency_stop_active:
            log.error("[DroneAgent] Refusing takeoff during emergency stop")
            return False
        height = self._positive_finite(height, "height")
        speed = min(
            self.max_z_speed,
            self._positive_finite(speed, "speed"),
        )
        baseline = self._fresh_height_snapshot()
        baseline_height = None if baseline is None else baseline["height"]

        with self._control_transport_lock:
            if self.emergency_stop_active:
                self.mission_phase = self.PHASE_FAULT
                log.error(
                    "[DroneAgent] Emergency stop arrived before TAKEOFF handoff"
                )
                return False
            self.mission_phase = self.PHASE_TAKEOFF
            if not self.set_uav_control_cmd_to_local("TAKEOFF"):
                self.mission_phase = self.PHASE_FAULT
                return False

            # Lock the mission transition as soon as TAKEOFF is accepted, but
            # keep periodic joystick publication disabled until lift-off.
            self.depart_flag = True
            self.departed = False
        if not self._wait_for_takeoff(baseline_height):
            self._command_safe_hover("takeoff was not confirmed before timeout")
            self.mission_phase = self.PHASE_FAULT
            return False

        self.departed = True
        if not self._climb_to_height(height, speed):
            self._command_safe_hover(
                "mission altitude was not reached before timeout"
            )
            self.mission_phase = self.PHASE_FAULT
            return False

        if not self.set_uav_control_cmd_to_local("HOVER"):
            self.mission_phase = self.PHASE_FAULT
            return False
        self.mission_phase = self.PHASE_POSITIONING
        log.success(
            f"[DroneAgent] Reached mission altitude {height:.2f} m"
        )
        return True

    def _wait_for_touchdown(self, start_height):
        deadline = self._clock() + self.landing_timeout
        descent_seen = (
            start_height is not None
            and start_height <= self.landing_ground_threshold
        )
        stable_since = None
        last_confirm_attempt = float("-inf")
        landing_confirmed = False

        while self._clock() < deadline:
            if (
                self.emergency_stop_active
                and self.mission_phase != self.PHASE_LANDING
            ):
                return False
            now = self._clock()
            state = self._fresh_height_snapshot(now)
            if state is None:
                stable_since = None
                self._sleep(0.05)
                continue

            height = state["height"]
            if start_height is not None and height <= start_height - 0.1:
                descent_seen = True

            if (
                not landing_confirmed
                and height <= self.landing_confirm_height
                and now - last_confirm_attempt >= 1.0
            ):
                last_confirm_attempt = now
                if self.set_uav_control_cmd_to_local("COFIRMLAND"):
                    landing_confirmed = True
                    log.success("[DroneAgent] Low-altitude landing confirmed")

            touchdown_candidate = (
                descent_seen
                and landing_confirmed
                and height <= self.landing_ground_threshold
                and abs(state["vertical_speed"]) <= self.velocity_tolerance
            )
            if touchdown_candidate:
                if stable_since is None:
                    stable_since = now
                elif now - stable_since >= self.landing_stable_window:
                    return True
            else:
                stable_since = None
            self._sleep(0.05)
        return False

    def _complete_landing(self):
        if not self.set_uav_control_cmd_to_local("OFFCONTROL"):
            log.error(
                "[DroneAgent] OFFCONTROL was not accepted; retaining landing "
                "state and keeping joystick publication disabled"
            )
            return False
        self.depart_flag = False
        self.departed = False
        self.mission_phase = (
            self.PHASE_FAULT
            if self.emergency_stop_active
            else self.PHASE_IDLE
        )
        self._landing_start_height = None
        self.gv_state_supervisor.clear()
        self._reset_gv_source_log()
        self.reset_pd_controller()
        log.success("[DroneAgent] Landing completed and confirmed")
        return True

    def return_to_car_and_land(self):
        """Return above the GV, stop guidance, land, and confirm touchdown."""
        if self.emergency_stop_active:
            log.error(
                "[DroneAgent] Return transition blocked by latched emergency "
                "stop"
            )
            return False
        if self.mission_phase == self.PHASE_LANDING:
            if self._wait_for_touchdown(self._landing_start_height):
                return self._complete_landing()
            log.error("[DroneAgent] Touchdown was not confirmed before timeout")
            return False

        if not self.stop_follow_mission():
            self._command_safe_hover("guidance thread could not be stopped")
            self.mission_phase = self.PHASE_FAULT
            return False

        height_state = self._fresh_height_snapshot()
        if height_state is None:
            self._command_safe_hover(
                "height state was stale before guarded return"
            )
            self.mission_phase = self.PHASE_FAULT
            return False
        return_height = height_state["height"]
        descent_height = min(
            return_height,
            self.landing_approach_height,
        )

        self.mission_phase = self.PHASE_RETURNING
        log.info("[DroneAgent] Reducing lead distance at the current altitude")
        if not self._complete_guidance_stage(
            height=return_height,
            guiding_range=0.0,
            description="horizontal return",
        ):
            return False

        self.mission_phase = self.PHASE_DESCENDING
        log.info("[DroneAgent] Horizontal return verified; descending")
        if not self._complete_guidance_stage(
            height=descent_height,
            guiding_range=0.0,
            description="guarded descent",
        ):
            return False

        # The guidance thread is stopped before LAND. Push one acknowledged
        # zero command so the executor cannot retain the final approach speed.
        if not self._send_zero_velocity():
            self._command_safe_hover(
                "zero-velocity handoff was not acknowledged"
            )
            self.mission_phase = self.PHASE_FAULT
            return False
        if not self.set_uav_control_cmd_to_local("HOVER"):
            self.mission_phase = self.PHASE_FAULT
            return False

        height_state = self._fresh_height_snapshot()
        if height_state is None:
            self._command_safe_hover("height state became stale before landing")
            self.mission_phase = self.PHASE_FAULT
            return False
        self._landing_start_height = height_state["height"]

        # Stop periodic velocity publication before issuing LAND. The same
        # transport lock serializes the emergency callback with this state
        # transition: either emergency hover finishes before LAND, or LAND
        # wins and later callbacks cannot re-enable joystick control.
        self.departed = False
        with self._control_transport_lock:
            if self.emergency_stop_active:
                self.mission_phase = self.PHASE_FAULT
                log.error(
                    "[DroneAgent] Emergency stop arrived before LAND handoff"
                )
                return False
            self.mission_phase = self.PHASE_LANDING
            land_acknowledged = self.set_uav_control_cmd_to_local("LAND")
        if not land_acknowledged:
            log.error(
                "[DroneAgent] LAND was not accepted or its result is "
                "ambiguous; retaining landing state without joystick commands"
            )

        if not self._wait_for_touchdown(self._landing_start_height):
            log.error("[DroneAgent] Touchdown was not confirmed before timeout")
            return False
        return self._complete_landing()

    def depart_and_start_follow(
        self,
        height=DEFAULT_HEIGHT,
        guiding_range=DEFAULT_GUIDING_RANGE,
    ):
        """Prepare one mission, reach its guiding pose, then enter escort."""
        if self.emergency_stop_active:
            log.error("[DroneAgent] Refusing mission start during emergency stop")
            return False
        mission_id = get_mission_id(self.url_remote)
        if mission_id is None:
            log.error(
                "[DroneAgent] Mission ID unavailable; refusing takeoff"
            )
            return False

        remote_config = get_follow_config(self.url_remote)
        if remote_config:
            height = remote_config["height"]
            guiding_range = remote_config["guiding_range"]
            log.success(
                "[DroneAgent] Applied remote escort configuration: "
                f"D={guiding_range:.2f} m, H={height:.2f} m"
            )
        else:
            log.warn(
                "[DroneAgent] Remote D/H unavailable; using fallback "
                f"D={guiding_range:.2f} m, H={height:.2f} m"
            )

        height = self._positive_finite(height, "height")
        guiding_range = self._nonnegative_finite(
            guiding_range, "guiding_range"
        )
        mission_id = str(mission_id)
        self.gv_state_supervisor.begin_mission(mission_id)
        self._reset_gv_source_log()
        with self._uav_state_lock:
            if (
                self._uav_state_snapshot is not None
                and self._uav_state_snapshot["mission_id"] != mission_id
            ):
                self._uav_state_snapshot = None
                self.pos[0], self.pos[1] = None, None
                self.pre_pos[0], self.pre_pos[1] = None, None
                self.pre_t = -1.0
                self.vx = 0.0
                self.vy = 0.0
            self._height_state_snapshot = None
            self.pos[2] = None
            self.pre_pos[2] = None
            self.vz = 0.0
            self.active_mission_id = mission_id

        self.is_gv_state_stale = False
        self._holding_stale_gv_reference = False
        self.hover_confirmed = False
        self.last_hover_attempt = float("-inf")
        self.mission_phase = self.PHASE_PREPARING
        self.reset_pd_controller()

        if not self.stop_follow_mission():
            self.mission_phase = self.PHASE_FAULT
            return False
        if not self._wait_for_preflight():
            log.error(
                "[DroneAgent] Preflight state/link confirmation timed out; "
                "takeoff remains inhibited"
            )
            self.mission_phase = self.PHASE_FAULT
            return False
        if not self.send_depart(height=height):
            return False
        if not self.start_follow_mission(
            height=height,
            guiding_range=guiding_range,
        ):
            self._command_safe_hover("positioning controller failed to start")
            self.mission_phase = self.PHASE_FAULT
            return False

        reached = self._wait_for_guiding_pose(
            height=height,
            guiding_range=guiding_range,
            timeout=self.positioning_timeout,
            abort_on_stop_order=True,
        )
        if not reached:
            self.stop_follow_mission()
            self._command_safe_hover(
                "guiding pose was not reached before timeout"
            )
            self.mission_phase = self.PHASE_FAULT
            return False

        self.depart_flag = True
        self.mission_phase = self.PHASE_ESCORT
        log.success("[DroneAgent] Guiding pose reached; escort active")
        return True
