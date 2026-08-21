import json
import threading
import time

import Tools.LogUtils as log
from Tools.ConfigUtils import read_config
from Tools.LoraTools import LoRaSX126X
from Tools.RequestTools import get_raw_msg
from Tools.UploadSpeedUtils import SpeedCaculator


class SourceHealth:
    """Track sustained source failures with a stable-recovery window."""

    def __init__(self, failure_threshold, recovery_successes):
        self.failure_threshold = max(1, int(failure_threshold))
        self.recovery_successes = max(1, int(recovery_successes))
        self.failures = 0
        self.recoveries = 0
        self.degraded = False

    def observe(self, succeeded):
        previous = self.degraded
        if succeeded:
            self.failures = 0
            if self.degraded:
                self.recoveries += 1
                if self.recoveries >= self.recovery_successes:
                    self.degraded = False
                    self.recoveries = 0
        else:
            self.recoveries = 0
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.degraded = True
        return previous, self.degraded


class LoraSender:
    def __init__(self, config_path, local_url, remote_url=None):
        config = read_config(config_path)
        lora_config = config["LoraConfigs"]
        self.msg_config = tuple(config["Msgs"])
        self.send_frequency = float(config["send_frequency"])
        if self.send_frequency <= 0:
            raise ValueError("send_frequency must be positive")
        self.heartbeat_intervals = {
            msg: float(
                config.get("HeartbeatIntervals", {}).get(
                    msg,
                    config.get("heartbeat_interval", 0.25),
                )
            )
            for msg in self.msg_config
        }
        if any(value <= 0 for value in self.heartbeat_intervals.values()):
            raise ValueError("LoRa heartbeat intervals must be positive")
        self.minimum_send_intervals = {
            msg: float(
                config.get("MinimumSendIntervals", {}).get(msg, 0.0)
            )
            for msg in self.msg_config
        }
        if any(value < 0 for value in self.minimum_send_intervals.values()):
            raise ValueError("LoRa minimum send intervals cannot be negative")
        self.emergency_active_heartbeat_interval = float(
            config.get("EmergencyActiveHeartbeatInterval", 0.2)
        )
        if self.emergency_active_heartbeat_interval <= 0:
            raise ValueError(
                "EmergencyActiveHeartbeatInterval must be positive"
            )

        self.local_url = local_url.rstrip("/")
        self.remote_url = (
            remote_url.rstrip("/")
            if remote_url and remote_url != "REMOTE_URL"
            else self.local_url
        )
        self.msg_sources = config.get("MsgSources", {})
        self.stop_flag = False
        self.node = LoRaSX126X(
            serial_num=lora_config['serial'],
            freq=lora_config['freq'],
            addr=lora_config['addr'],
            power=lora_config['power'],
            air_speed=lora_config['ari_speed'],
        )
        self.speed_clc = SpeedCaculator()
        self.thread_list = []
        self.latest_data = {msg: None for msg in self.msg_config}
        self.last_sent_data = {msg: None for msg in self.msg_config}
        self.last_sent_at = {msg: None for msg in self.msg_config}
        self.data_lock = threading.Lock()
        self.radio_lock = threading.Lock()
        failure_threshold = config.get("SourceFailureThreshold", 3)
        recovery_successes = config.get("SourceRecoverySuccesses", 3)
        self.source_health = {
            msg: SourceHealth(failure_threshold, recovery_successes)
            for msg in self.msg_config
        }
        self.start_threads()
        log.success("  [LoRa Sender] Threads started")

    def _source_url(self, msg_type):
        source = str(self.msg_sources.get(msg_type, "local")).lower()
        return self.remote_url if source == "remote" else self.local_url

    def send_data(self, msg_name, raw_data):
        payload = json.dumps(
            raw_data,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        with self.radio_lock:
            self.node.send(f":{msg_name}:{payload}")

    @staticmethod
    def _message_identity(msg_type, data):
        if (
            msg_type == "emergencyData"
            and isinstance(data, list)
            and len(data) >= 2
        ):
            return tuple(data[:2])
        return data

    def _heartbeat_interval(self, msg_type, data):
        if (
            msg_type == "emergencyData"
            and isinstance(data, list)
            and data
            and data[0] is True
        ):
            return self.emergency_active_heartbeat_interval
        return self.heartbeat_intervals[msg_type]

    def _send_state(self, msg_type, now):
        with self.data_lock:
            latest = self.latest_data[msg_type]
            last_data = self.last_sent_data[msg_type]
            last_time = self.last_sent_at[msg_type]
        if latest is None:
            return None
        elapsed = float("inf") if last_time is None else now - last_time
        changed = (
            self._message_identity(msg_type, latest)
            != self._message_identity(msg_type, last_data)
        )
        due = changed or elapsed >= self._heartbeat_interval(
            msg_type, latest
        )
        minimum_met = (
            last_time is None
            or elapsed >= self.minimum_send_intervals[msg_type]
        )
        return {
            "latest": latest,
            "changed": changed,
            "due": due and minimum_met,
            "active_emergency": (
                msg_type == "emergencyData"
                and isinstance(latest, list)
                and bool(latest)
                and latest[0] is True
            ),
        }

    def send_pending(self, msg_type, now=None):
        now = time.monotonic() if now is None else now
        state = self._send_state(msg_type, now)
        if state is None or not state["due"]:
            return False

        latest = state["latest"]
        self.send_data(msg_type, latest)
        with self.data_lock:
            self.last_sent_data[msg_type] = latest
            self.last_sent_at[msg_type] = now
        log.success(
            f"      [LoRa Sender type->{msg_type}] send {latest} "
            f"succeeded, rate "
            f"{self.speed_clc[f'{msg_type}_tx']:.2f} ops/s"
        )
        return True

    def send_next(self, now=None):
        now = time.monotonic() if now is None else now
        states = {
            msg: self._send_state(msg, now)
            for msg in self.msg_config
        }
        urgent = [
            msg
            for msg, state in states.items()
            if (
                state is not None
                and state["due"]
                and (
                    state["active_emergency"]
                    or (
                        msg == "emergencyData"
                        and state["changed"]
                    )
                )
            )
        ]
        normal = [
            msg
            for msg, state in states.items()
            if (
                state is not None
                and state["due"]
                and msg != "emergencyData"
            )
        ]
        background = [
            msg
            for msg, state in states.items()
            if (
                state is not None
                and state["due"]
                and msg == "emergencyData"
                and msg not in urgent
            )
        ]
        candidates = urgent or normal or background
        if not candidates:
            return False
        return self.send_pending(candidates[0], now=now)

    def send_loop(self):
        period = 1 / self.send_frequency
        while not self.stop_flag:
            started_at = time.monotonic()
            try:
                self.send_next(started_at)
            except Exception as error:
                log.error(
                    f"      [LoRa Sender] scheduled send failed, error "
                    f"{error}"
                )
            delay = period - (time.monotonic() - started_at)
            if delay > 0:
                time.sleep(delay)

    def get_msg_once(self, msg_type):
        value = get_raw_msg(self._source_url(msg_type), msg_type)
        health = self.source_health[msg_type]
        previous, current = health.observe(value is not None)
        if not previous and current:
            log.warn(
                f"      [LoRa Sender type->{msg_type}] source degraded "
                f"after {health.failures} consecutive failures"
            )
        elif previous and not current:
            log.success(
                f"      [LoRa Sender type->{msg_type}] source recovered "
                "after stable successful polls"
            )
        if value is None:
            return False
        with self.data_lock:
            self.latest_data[msg_type] = value
        log.success(
            f"      [LoRa Sender type->{msg_type}] get {value} "
            f"succeeded, rate "
            f"{self.speed_clc[f'{msg_type}_get']:.2f} ops/s"
        )
        return True

    def get_msg(self, msg_type):
        while not self.stop_flag:
            try:
                self.get_msg_once(msg_type)
            except Exception as error:
                self.source_health[msg_type].observe(False)
                log.error(
                    f"      [LoRa Sender type->{msg_type}] get failed, "
                    f"error {error}"
                )
            time.sleep(1 / self.send_frequency)

    def start_threads(self):
        for msg in self.msg_config:
            self.thread_list.append(
                threading.Thread(
                    target=self.get_msg,
                    args=(msg,),
                    name=f"lora-source-{msg}",
                )
            )
            self.thread_list[-1].start()
            log.success(f"      [LoRa Sender source->{msg}] started")
        self.thread_list.append(
            threading.Thread(
                target=self.send_loop,
                name="lora-sender",
            )
        )
        self.thread_list[-1].start()
        log.success("      [LoRa Sender] scheduler started")

    def close(self):
        self.stop_flag = True
        self.node.close()
        for thread in self.thread_list:
            thread.join(timeout=3.0)
            if thread.is_alive():
                log.warn(
                    f"  [LoRa Sender] Thread {thread.name} "
                    "did not stop in time"
                )
        log.error("  [LoRa Sender] Exiting")


if __name__ == "__main__":
    import sys

    sender = LoraSender(
        config_path=sys.argv[1],
        local_url=sys.argv[2],
        remote_url=sys.argv[3] if len(sys.argv) > 3 else None,
    )
    log.success("  [LoRa Sender] Started. Press any key to exit.. \n")
    input()
    sender.close()
    exit(2)
