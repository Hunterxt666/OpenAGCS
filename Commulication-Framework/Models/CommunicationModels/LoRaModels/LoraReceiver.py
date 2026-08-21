import ast
import json
import math
import threading
import time

import Tools.LogUtils as log
from Tools.ConfigUtils import read_config
from Tools.LoraTools import LoRaSX126X
from Tools.RequestTools import send_lora_data
from Tools.UploadSpeedUtils import SpeedCaculator


class LoraReceiver:
    def __init__(self, config_path, local_url):
        config = read_config(config_path)
        lora_config = config["LoraConfigs"]
        self.node = LoRaSX126X(
            serial_num=lora_config['serial'],
            freq=lora_config['freq'],
            addr=lora_config['addr'],
            power=lora_config['power'],
            air_speed=lora_config['ari_speed'],
        )
        self.rec_feq = float(config["rec_frequency"])
        if self.rec_feq <= 0:
            raise ValueError("rec_frequency must be positive")
        self.stop_flag = False
        self.url = local_url
        self.msg_jud = tuple(config["rec_msg"])
        self.speed_clc = SpeedCaculator()
        self.latest_data = {msg: None for msg in self.msg_jud}
        self.latest_generation = {msg: 0 for msg in self.msg_jud}
        self.latest_received_at = {msg: None for msg in self.msg_jud}
        self.uploaded_generation = {msg: 0 for msg in self.msg_jud}
        self.pre_data = {msg: None for msg in self.msg_jud}
        self.data_lock = threading.Lock()
        self.thread_list = []
        self.start_rec_process()
        log.success("  [LoRa Receiver] Initialization complete")

    @staticmethod
    def decode_frame(frame):
        if not isinstance(frame, str):
            raise ValueError("LoRa frame must be text")
        prefix, separator, remainder = frame.partition(":")
        if prefix or not separator:
            raise ValueError("LoRa frame must start with ':'")
        msg_type, separator, payload = remainder.partition(":")
        if not msg_type or not separator:
            raise ValueError("LoRa frame has no message type or payload")
        try:
            return msg_type, json.loads(payload)
        except json.JSONDecodeError:
            # Accept frames emitted by older deployments during a rolling
            # upgrade, then always re-upload structured JSON locally.
            return msg_type, ast.literal_eval(payload)

    def record_frame(self, frame, received_at=None):
        msg_type, payload = self.decode_frame(frame)
        if msg_type not in self.msg_jud:
            return False
        received_at = (
            time.time() if received_at is None else float(received_at)
        )
        if not math.isfinite(received_at):
            raise ValueError("LoRa receive time must be finite")
        with self.data_lock:
            self.latest_data[msg_type] = payload
            self.latest_generation[msg_type] += 1
            self.latest_received_at[msg_type] = received_at
        log.success(
            f"      [LoRa Receiver type->{msg_type}] received {payload} "
            f"succeeded, rate "
            f"{self.speed_clc[f'{msg_type}_rec']:.2f} ops/s"
        )
        return True

    def rec_fun(self):
        while not self.stop_flag:
            try:
                frame = self.node.receive()
                if frame is not None:
                    self.record_frame(frame)
            except Exception as error:
                log.error(f"      [LoRa Receiver] Receive error {error}")
            time.sleep(1 / self.rec_feq)

    def upload_latest(self, msg_type):
        with self.data_lock:
            generation = self.latest_generation[msg_type]
            payload = self.latest_data[msg_type]
            received_at = self.latest_received_at[msg_type]
            uploaded_generation = self.uploaded_generation[msg_type]
        if payload is None or generation == uploaded_generation:
            return None

        sent = send_lora_data(
            url=self.url,
            data_type=msg_type,
            data=payload,
            received_at=received_at,
        )
        if sent:
            with self.data_lock:
                self.uploaded_generation[msg_type] = generation
                self.pre_data[msg_type] = payload
            log.success(
                f"      [LoRa Receiver type->{msg_type}] upload {payload} "
                f"succeeded, rate "
                f"{self.speed_clc[f'{msg_type}_rx']:.2f} ops/s"
            )
        else:
            log.warn(
                f"      [LoRa Receiver type->{msg_type}] local upload "
                "failed; packet will be retried"
            )
        return sent

    def send_data_to_local(self):
        while not self.stop_flag:
            for msg_type in self.msg_jud:
                try:
                    self.upload_latest(msg_type)
                except Exception as error:
                    log.error(
                        f"      [LoRa Receiver type->{msg_type}] upload "
                        f"failed, error {error}"
                    )
            time.sleep(1 / self.rec_feq)

    def start_rec_process(self):
        self.thread_list = [
            threading.Thread(target=self.rec_fun, name="lora-receiver"),
            threading.Thread(
                target=self.send_data_to_local,
                name="lora-local-uploader",
            ),
        ]
        for thread in self.thread_list:
            thread.start()
        log.success("      [LoRa Receiver] started")

    def close(self):
        self.stop_flag = True
        self.node.close()
        for thread in self.thread_list:
            thread.join(timeout=3.0)
            if thread.is_alive():
                log.warn(
                    f"  [LoRa Receiver] Thread {thread.name} "
                    "did not stop in time"
                )
        log.error("  [LoRa Receiver] Exiting")


if __name__ == "__main__":
    import sys

    receiver = LoraReceiver(
        config_path=sys.argv[1],
        local_url=sys.argv[2],
    )
    log.success("  [LoRa Receiver] Started. Press any key to exit.. \n")
    input()
    receiver.close()
    exit(3)
