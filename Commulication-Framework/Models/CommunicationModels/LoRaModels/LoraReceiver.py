import threading
import Tools.LogUtils as log
import ast
import time
from Tools.ConfigUtils import read_config
from Tools.RequestTools import send_lora_data
from Tools.UploadSpeedUtils import SpeedCaculator
from Tools.LoraTools import LoRaSX126X


class LoraReceiver:
    def __init__(self, config_path, local_url):
        config = read_config(config_path)
        lora_config = config["LoraConfigs"]
        self.node = LoRaSX126X(serial_num=lora_config['serial'], freq=lora_config['freq'], addr=lora_config['addr'],
                               power=lora_config['power'], air_speed=lora_config['ari_speed'])
        self.rec_feq = config["rec_frequency"]
        self.stop_flag = False
        self.url = local_url
        self.msg_jud = config["rec_msg"]
        self.speed_clc = SpeedCaculator()
        self.latest_data = {msg: None for msg in self.msg_jud}
        self.pre_data = {msg: None for msg in self.msg_jud}
        self.receive_process = self.start_rec_process()
        log.error("  [LoRa Receiver] Initialization complete")

    def rec_fun(self):
        while not self.stop_flag:
            try:
                msg = self.node.receive()
                if msg is not None:
                    msg = msg.split(":")
                    if len(msg) < 3 or msg[1] not in self.msg_jud or self.latest_data[msg[1]] == msg[2]:
                        time.sleep(1 / self.rec_feq)
                        continue
                    self.latest_data[msg[1]] = msg[2]
                    log.success(f"      [LoRa Receiver type->{msg[1]}] received {msg[2]} succeeded, rate {self.speed_clc[f'{msg[1]}_rec']:.2f} ops/s")
            except Exception as e:
                log.error(f"      [LoRa Receiver] Receive error {e}")
            time.sleep(1 / self.rec_feq)

    def send_data_to_local(self):
        while not self.stop_flag:
            for msg_type in self.msg_jud:
                if self.latest_data[msg_type] is not None and self.pre_data[msg_type] != self.latest_data[msg_type]:
                    try:
                        latest_msg = self.latest_data[msg_type]
                        send_lora_data(url=self.url, data_type=msg_type, data=ast.literal_eval(latest_msg))
                        self.pre_data[msg_type] = latest_msg
                        log.success(f"      [LoRa Receiver type->{msg_type}] upload {latest_msg} succeeded, rate {self.speed_clc[f'{msg_type}_rx']:.2f} ops/s")
                    except Exception as e:
                        log.error(f"      [LoRa Receiver type->{msg_type}] upload failed, error {e}")
            time.sleep(1 / self.rec_feq)

    def start_rec_process(self):
        thread = threading.Thread(target=self.rec_fun)
        thread.start()
        thread = threading.Thread(target=self.send_data_to_local)
        thread.start()
        log.success("      [LoRa Receiver] started")
        return thread

    def close(self):
        self.stop_flag = True
        self.receive_process.join()
        log.error("  [LoRa Receiver] Exiting")


if __name__ == "__main__":
    import sys
    lora_sender_model = LoraReceiver(
        config_path=sys.argv[1], local_url=sys.argv[2]
    )
    log.success("  [LoRa Receiver] Started. Press any key to exit.. \n")
    input()
    lora_sender_model.close()
    exit(3)
