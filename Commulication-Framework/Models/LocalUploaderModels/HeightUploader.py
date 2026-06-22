from Tools.ConfigUtils import read_config
import serial
import time
import Tools.LogUtils as log
from Tools.DBUtils import create_height_data_table, upload_height_data
from Tools.ResolveDataUtils import resolve_height_data
from threading import Thread
from Tools.UploadSpeedUtils import SpeedCaculator
from Tools.RequestTools import send_height
from datetime import datetime


class HeightUploader:
    def __init__(self, time_str, config_path, agent, remote_url, local_url):
        log.info("  [Height Uploader] Initializing..")
        config = read_config(config_path)
        self.speed_test = SpeedCaculator()
        self.agent = agent
        self.height_data = [None, None]
        self.pre_data = {"send_local": [None, None], "send_remote": [None, None], "send_db": [None, None]}
        self.remote_url = remote_url
        self.local_url = local_url
        log.info("    [Height Uploader] Initializing module serial port..")
        self.serial = serial.Serial(config["SerialConfig"]["port"], config["SerialConfig"]["rate"], timeout=1)
        self.serial.reset_input_buffer()
        log.success("    [Height Uploader] Serial port connected")
        # self.table_name = f"{time_str}_{agent}_height_data"
        # self.sql_config = config['DBconfig']
        # log.info(f"    [Height Uploader] Initializing SQL, creating height table {self.table_name}..")
        # create_height_data_table(self.table_name, self.sql_config)
        # log.success(f"    [Height Uploader] SQL initialized, height table {self.table_name} created")
        self.stop_flag = False
        self.task_list = []
        self.start_mission()
        log.success("  [Height Uploader] Initialization complete, starting upload")

    def start_mission(self):
        log.info("    [Height Uploader] Preparing to start upload tasks...")
        self.task_list.append(Thread(target=self.get_height_str))
        self.task_list.append(Thread(target=self.upload_height_data_to_local))
        self.task_list.append(Thread(target=self.upload_height_data_to_remote))
        # self.task_list.append(Thread(target=self.upload_height_data_to_db))
        for t in self.task_list:
            t.start()
        log.success("    [Height Uploader] Upload tasks started")

    def get_height_str(self):
        log.info("      [Height Uploader] [Get height data] starting...")
        while not self.stop_flag:
            try:
                if self.serial.in_waiting > 0:
                    rx_data = self.serial.readline()  # Read incoming data
                    if rx_data.find(b"Height") != -1:
                        self.height_data = [datetime.now(), resolve_height_data(rx_data)]
                        log.success(f"      [Height Uploader] [Get height data] success, rate {self.speed_test['get_height_data']:.2f} ops/s")
            except Exception as e:
                log.error(f"      [Height Uploader] [Get height data] error: {e}")
            time.sleep(0.05)
        log.error("      [Height Uploader] [Get height data] exiting")

    def upload_height_data_to_local(self):
        log.info("      [Height Uploader] [Local height upload] starting...")
        while not self.stop_flag:
            try:
                if self.pre_data["send_local"][0] != self.height_data[0] and self.height_data[0]:
                    ut, resolve_data = self.height_data[0], self.height_data[1]
                    if resolve_data:
                        send_height(
                            url=self.local_url, time=ut, height=resolve_data, agent=self.agent
                        )
                    log.success(f"        [Height Uploader] [Local height upload] succeeded, rate {self.speed_test['get_local_height_data']:.2f} ops/s, height {resolve_data}m")
                    self.pre_data["send_local"] = [ut, resolve_data]
            except Exception as e:
                log.error(f"        [Height Uploader] [Local height upload] error {e}")
                time.sleep(1)
            time.sleep(0.05)
        log.error("      [Height Uploader] [Local height upload] exiting")

    def upload_height_data_to_remote(self):
        log.info("      [Height Uploader] [Remote height upload] starting...")
        while not self.stop_flag:
            try:
                if self.pre_data["send_remote"][0] != self.height_data[0] and self.height_data[0]:
                    ut, resolve_data = self.height_data[0], self.height_data[1]
                    if resolve_data:
                        send_height(
                            url=self.remote_url, time=ut, height=resolve_data, agent=self.agent
                        )
                    log.success(
                        f"        [Height Uploader] [Remote height upload] succeeded, rate {self.speed_test['get_remote_height_data']:.2f} ops/s, height {resolve_data}m")
                    self.pre_data["send_remote"] = [ut, resolve_data]
            except Exception as e:
                log.error(f"        [Height Uploader] [Remote height upload] error {e}")
                time.sleep(1)
            time.sleep(0.05)
        log.error("      [Height Uploader] [Remote height upload] exiting")

    def upload_height_data_to_db(self):
        log.info("      [Height Uploader] [DB height upload] starting...")
        while not self.stop_flag:
            try:
                if self.pre_data["send_db"][0] != self.height_data[0] and self.height_data[0]:
                    ut, resolve_data = self.height_data[0], self.height_data[1]
                    if resolve_data:
                        upload_height_data(ut, resolve_data, self.table_name, self.sql_config)
                    log.success(
                        f"        [Height Uploader] [DB height upload] succeeded, rate {self.speed_test['get_db_height_data']:.2f} ops/s, height {resolve_data}m")
                    self.pre_data["send_db"] = [ut, resolve_data]
            except Exception as e:
                log.error(f"        [Height Uploader] [DB height upload] error {e}")
                time.sleep(1)
            time.sleep(0.05)
        log.error("      [Height Uploader] [DB height upload] exiting")

    def stop(self):
        self.stop_flag = True
        log.info("  [Height Uploader] Stopping, waiting for tasks to finish...")
        for t in self.task_list:
            t.join()
        log.error("  [Height Uploader] Stopped, upload ended")


if __name__ == "__main__":
    import sys
    location_model = HeightUploader(
        config_path=sys.argv[1], time_str=sys.argv[2], agent=sys.argv[3],
        remote_url=sys.argv[4], local_url=sys.argv[5]
    )
    log.success("  [Height Uploader] Started. Press any key to exit.. \n")
    input()
    location_model.stop()
    exit(3)
