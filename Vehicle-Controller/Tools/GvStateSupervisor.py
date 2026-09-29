"""Fresh-state selection for cellular and LoRa GV telemetry."""

import math
import threading
import time


class GvStateSupervisor:
    """Select cellular GV state, using LoRa only while cellular is unusable."""

    def __init__(
        self,
        freshness_timeout=0.3,
        stale_state_hold_timeout=None,
        clock_skew_tolerance=0.0,
        link_heartbeat_timeout=None,
        link_failure_threshold=3,
        cellular_recovery_window=1.0,
        clock=time.monotonic,
    ):
        if not math.isfinite(freshness_timeout) or freshness_timeout <= 0:
            raise ValueError("freshness_timeout must be a positive finite value")
        if (
            not math.isfinite(clock_skew_tolerance)
            or clock_skew_tolerance < 0
            or clock_skew_tolerance > freshness_timeout
        ):
            raise ValueError(
                "clock_skew_tolerance must be finite and in "
                "[0, freshness_timeout]"
            )
        self.freshness_timeout = float(freshness_timeout)
        if stale_state_hold_timeout is None:
            stale_state_hold_timeout = max(2.0, self.freshness_timeout)
        if (
            not math.isfinite(stale_state_hold_timeout)
            or stale_state_hold_timeout < self.freshness_timeout
        ):
            raise ValueError(
                "stale_state_hold_timeout must be finite and no smaller than "
                "freshness_timeout"
            )
        self.stale_state_hold_timeout = float(stale_state_hold_timeout)
        self.clock_skew_tolerance = float(clock_skew_tolerance)
        if link_heartbeat_timeout is None:
            link_heartbeat_timeout = freshness_timeout
        if (
            not math.isfinite(link_heartbeat_timeout)
            or link_heartbeat_timeout <= 0
        ):
            raise ValueError(
                "link_heartbeat_timeout must be a positive finite value"
            )
        if (
            isinstance(link_failure_threshold, bool)
            or int(link_failure_threshold) != link_failure_threshold
            or link_failure_threshold <= 0
        ):
            raise ValueError("link_failure_threshold must be a positive integer")
        if (
            not math.isfinite(cellular_recovery_window)
            or cellular_recovery_window <= 0
        ):
            raise ValueError(
                "cellular_recovery_window must be a positive finite value"
            )
        self.link_heartbeat_timeout = float(link_heartbeat_timeout)
        self.link_failure_threshold = int(link_failure_threshold)
        self.cellular_recovery_window = float(cellular_recovery_window)
        self._clock = clock
        self._states = {}
        self._last_sample_ids = {}
        self._last_sensed_at = {}
        self._link_last_success = {}
        self._link_failures = {}
        self._active_source = "cellular"
        self._cellular_recovery_since = None
        self._last_selected_sensed_at = None
        self._mission_id = None
        self._lock = threading.Lock()

    def begin_mission(self, mission_id):
        """Activate one telemetry epoch and invalidate in-flight old packets."""
        if (
            mission_id is None
            or isinstance(mission_id, bool)
            or not str(mission_id).strip()
        ):
            raise ValueError("mission_id must not be empty")
        mission_id = str(mission_id)
        with self._lock:
            changed = mission_id != self._mission_id
            self._mission_id = mission_id
            self._states.clear()
            self._link_last_success.clear()
            self._link_failures.clear()
            self._active_source = "cellular"
            self._cellular_recovery_since = None
            self._last_selected_sensed_at = None
            if changed:
                self._last_sample_ids.clear()
                self._last_sensed_at.clear()
        return changed

    def observe_link(self, source, succeeded, observed_at=None):
        """Record one heartbeat/delivery result without refreshing state data."""
        if not source:
            raise ValueError("source must not be empty")
        if not isinstance(succeeded, bool):
            raise ValueError("succeeded must be boolean")
        if observed_at is None:
            observed_at = self._clock()
        observed_at = float(observed_at)
        if not math.isfinite(observed_at):
            raise ValueError("observed_at must be finite")

        with self._lock:
            if succeeded:
                self._link_last_success[source] = observed_at
                self._link_failures[source] = 0
            else:
                self._link_failures[source] = (
                    self._link_failures.get(source, 0) + 1
                )
                if source == "cellular":
                    self._cellular_recovery_since = None
            return self._link_is_healthy_locked(source, observed_at)

    def _link_is_healthy_locked(self, source, now):
        last_success = self._link_last_success.get(source)
        if last_success is None:
            return False
        age = now - last_success
        return (
            0.0 <= age <= self.link_heartbeat_timeout
            and self._link_failures.get(source, 0)
            < self.link_failure_threshold
        )

    @property
    def active_source(self):
        with self._lock:
            return self._active_source

    def link_health(self, now=None):
        """Return a point-in-time health snapshot for both transport links."""
        if now is None:
            now = self._clock()
        now = float(now)
        if not math.isfinite(now):
            raise ValueError("now must be finite")
        with self._lock:
            return {
                source: self._link_is_healthy_locked(source, now)
                for source in ("cellular", "lora")
            }

    def _select_locked(self, state):
        """Record one selection while keeping sensing time monotonic."""
        if state is None:
            return None
        sensed_at = state["sensed_at"]
        if (
            self._last_selected_sensed_at is not None
            and sensed_at < self._last_selected_sensed_at
        ):
            return None
        self._last_selected_sensed_at = sensed_at
        return state

    def update(
        self,
        source,
        mission_id,
        sample_id,
        position,
        yaw_degrees,
        sensed_at,
        height=None,
        velocity=None,
    ):
        """Store a genuinely new state sample.

        Repeated reads of the same ``sample_id`` do not refresh the receive
        time. Packets from an inactive mission epoch are also ignored. This
        method only maintains the data cache; callers must report independent
        transport or heartbeat results through ``observe_link``.
        """
        if not source:
            raise ValueError("source must not be empty")
        if mission_id is None:
            raise ValueError("mission_id must not be None")
        if len(position) != 2:
            raise ValueError("position must contain x and y")

        mission_id = str(mission_id)
        x, y = float(position[0]), float(position[1])
        yaw_degrees = float(yaw_degrees)
        sensed_at = float(sensed_at)
        if not all(math.isfinite(value) for value in (x, y, yaw_degrees, sensed_at)):
            raise ValueError("GV state values must be finite")
        if height is not None:
            height = float(height)
            if not math.isfinite(height):
                raise ValueError("GV height must be finite")
        if velocity is not None:
            if len(velocity) != 2:
                raise ValueError("GV velocity must contain east and north")
            velocity = tuple(float(value) for value in velocity)
            if not all(math.isfinite(value) for value in velocity):
                raise ValueError("GV velocity must be finite")

        received_at = self._clock()
        state = {
            "source": source,
            "sample_id": sample_id,
            "position": (x, y),
            "yaw_degrees": yaw_degrees,
            "height": height,
            "velocity": velocity,
            "sensed_at": sensed_at,
            "received_at": received_at,
        }

        with self._lock:
            if self._mission_id is None or mission_id != self._mission_id:
                return False
            if (
                self._last_sample_ids.get(source) == sample_id
                or sensed_at <= self._last_sensed_at.get(source, float("-inf"))
            ):
                return False
            self._states[source] = state
            self._last_sample_ids[source] = sample_id
            self._last_sensed_at[source] = sensed_at
        return True

    def select(self, now=None, current_sensed_at=None):
        """Return the paper's preferred usable state, or ``None``.

        Cellular is the primary transport. LoRa is considered only when the
        cellular state is unavailable, stale, non-causal, or its link is
        unhealthy. After a fallback, cellular must remain continuously usable
        for the recovery window before it becomes primary again. Transport
        freshness and heartbeat health are deliberately kept separate, and
        the selected sensing timestamp is never allowed to move backward.
        """
        if now is None:
            now = self._clock()
        now = float(now)
        if not math.isfinite(now):
            raise ValueError("now must be finite")
        if current_sensed_at is not None:
            current_sensed_at = float(current_sensed_at)
            if not math.isfinite(current_sensed_at):
                raise ValueError("current_sensed_at must be finite")

        with self._lock:
            hold_candidates = {
                state["source"]: dict(state)
                for state in self._states.values()
                if state["source"] in {"cellular", "lora"}
                if 0 <= now - state["received_at"] <= self.stale_state_hold_timeout
                and (
                    current_sensed_at is None
                    or -self.clock_skew_tolerance
                    <= current_sensed_at - state["sensed_at"]
                    <= self.stale_state_hold_timeout
                )
            }
            candidates = {
                source: state
                for source, state in hold_candidates.items()
                if now - state["received_at"] <= self.freshness_timeout
                and (
                    current_sensed_at is None
                    or current_sensed_at - state["sensed_at"]
                    <= self.freshness_timeout
                )
            }
            cellular_healthy = self._link_is_healthy_locked("cellular", now)
            lora_healthy = self._link_is_healthy_locked("lora", now)
            if self._last_selected_sensed_at is not None:
                candidates = {
                    source: state
                    for source, state in candidates.items()
                    if state["sensed_at"] >= self._last_selected_sensed_at
                }
                hold_candidates = {
                    source: state
                    for source, state in hold_candidates.items()
                    if state["sensed_at"] >= self._last_selected_sensed_at
                }

            cellular = (
                candidates.get("cellular") if cellular_healthy else None
            )
            lora = candidates.get("lora") if lora_healthy else None

            if self._active_source == "lora":
                if cellular is None:
                    self._cellular_recovery_since = None
                    selected = lora
                else:
                    if self._cellular_recovery_since is None:
                        self._cellular_recovery_since = now
                    cellular_recovered = (
                        now - self._cellular_recovery_since
                        >= self.cellular_recovery_window
                    )
                    selected = cellular if cellular_recovered else lora
            else:
                self._cellular_recovery_since = None
                selected = cellular if cellular is not None else lora

            if selected is None:
                # Paper policy: while all newly arriving states are stale, hold
                # the newest causally available reference for a bounded grace
                # period. The controller continues recomputing commands from
                # its current UAV state and enters hover only after the grace
                # period expires.
                selected = max(
                    hold_candidates.values(),
                    key=lambda state: state["sensed_at"],
                    default=None,
                )
                if selected is None:
                    return None

            selected = dict(selected)
            selected["is_stale"] = (
                now - selected["received_at"] > self.freshness_timeout
                or (
                    current_sensed_at is not None
                    and current_sensed_at - selected["sensed_at"]
                    > self.freshness_timeout
                )
            )

            accepted = self._select_locked(selected)
            if accepted is None:
                return None
            if selected["source"] != self._active_source:
                self._active_source = selected["source"]
            if selected["source"] == "cellular":
                self._cellular_recovery_since = None
            return accepted

    def clear(self, preserve_sample_ids=True):
        with self._lock:
            self._states.clear()
            self._link_last_success.clear()
            self._link_failures.clear()
            self._active_source = "cellular"
            self._cellular_recovery_since = None
            self._last_selected_sensed_at = None
            if not preserve_sample_ids:
                self._last_sample_ids.clear()
                self._last_sensed_at.clear()
