import threading

import Tools.LogUtils as log
import time
from Tools.ConfigUtils import read_config
from Tools.RequestTools import get_raw_msg
from Tools.LoraTools import LoRaSX126X
from Tools.UploadSpeedUtils import SpeedCaculator


class LoraSender:
    def __init__(self, config_path, local_url):
        config = read_config(config_path)
        lora_config = config["LoraConfigs"]
        self.msg_config = config["Msgs"]
        self.send_frequency = config["send_frequency"]
        self.url = local_url
        self.stop_flag = False
        self.node = LoRaSX126X(serial_num=lora_config['serial'], freq=lora_config['freq'], addr=lora_config['addr'],
                               power=lora_config['power'], air_speed=lora_config['ari_speed'])
        self.re = ""
        self.speed_clc = SpeedCaculator()
        self.thread_list = []
        self.start_threads()
        log.success("  [LoRa Sender] Threads started")

    def send_data(self, msg_name, raw_data):
        data = f":{msg_name}:{raw_data}"
        self.node.send(data)

    def send_msg(self, msg_type):
        pre_msg = ""
        while not self.stop_flag:
            if self.re != pre_msg:
                self.send_data(msg_type, self.re)
                pre_msg = self.re
                log.success(f"      [LoRa Sender type->{msg_type}] send {self.re} succeeded, rate {self.speed_clc[f'{msg_type}_tx']:.2f} ops/s")
            time.sleep(1 / self.send_frequency)

    def get_msg(self, msg_type):
        while not self.stop_flag:
            re = get_raw_msg(self.url, msg_type)
            if re is not None:
                self.re = re
                log.success(f"      [LoRa Sender type->{msg_type}] get {re} succeeded, rate {self.speed_clc[f'{msg_type}_get']:.2f} ops/s")
            time.sleep(1 / self.send_frequency)

    def start_threads(self):
        for msg in self.msg_config:
            self.thread_list.append(threading.Thread(target=self.get_msg, args=(msg,)))
            self.thread_list[-1].start()
            self.thread_list.append(threading.Thread(target=self.send_msg, args=(msg,)))
            self.thread_list[-1].start()
            log.success(f"      [LoRa Sender type->{msg}] started")

    def close(self):
        self.stop_flag = True
        for th in self.thread_list:
            th.join()
        log.error("  [LoRa Sender] Exiting")


if __name__ == "__main__":
    import sys
    lora_sender_model = LoraSender(
        config_path=sys.argv[1], local_url=sys.argv[2]
    )
    log.success("  [LoRa Sender] Started. Press any key to exit.. \n")
    input()
    lora_sender_model.close()
    exit(2)
