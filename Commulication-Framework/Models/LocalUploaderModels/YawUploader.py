from Tools.ConfigUtils import read_config
import serial
import time
import Tools.LogUtils as log
from Tools.DBUtils import create_orientation_data_table, upload_orientation_data
from Tools.PoseEstimationTool import Sensor
from threading import Thread
from Tools.UploadSpeedUtils import SpeedCaculator
from Tools.RequestTools import send_orientation
from datetime import datetime


class YawUploader:
    def __init__(self, time_str, config_path, agent, remote_url, local_url):
        log.info("  [Yaw Uploader] Initializing..")
        config = read_config(config_path)
        self.speed_test = SpeedCaculator()
        self.agent = agent
        self.yaw_data = [None, None]
        self.pre_data = {"send_local": [None, None], "send_remote": [None, None], "send_db": [None, None]}
        self.remote_url = remote_url
        self.local_url = local_url
        log.info("    [Yaw Uploader] Initializing module serial port..")
        self.serial = Sensor(config['SerialConfig']['port'])
        log.success("    [Yaw Uploader] Serial port connected")
        # self.table_name = f"{time_str}_{agent}_yaw_data"
        # self.sql_config = config['DBconfig']
        # log.info(f"    [Yaw Uploader] Initializing SQL, creating yaw table {self.table_name}..")
        # create_orientation_data_table(self.table_name, self.sql_config)
        # log.success(f"    [Yaw Uploader] SQL initialized, yaw table {self.table_name} created")
        self.stop_flag = False
        self.task_list = []
        self.start_mission()
        log.success("  [Yaw Uploader] Initialization complete, starting upload")

    def start_mission(self):
        log.info("    [Yaw Uploader] Preparing to start upload tasks...")
        self.task_list.append(Thread(target=self.get_yaw_str))
        self.task_list.append(Thread(target=self.upload_yaw_data_to_local))
        self.task_list.append(Thread(target=self.upload_yaw_data_to_remote))
        # self.task_list.append(Thread(target=self.upload_yaw_data_to_db))
        for t in self.task_list:
            t.start()
        log.success("    [Yaw Uploader] Upload tasks started")

    def get_yaw_str(self):
        log.info("      [Yaw Uploader] [Get yaw data] starting...")
        while not self.stop_flag:
            try:
                self.yaw_data = [datetime.now(), self.serial.yaw]
                log.success(f"      [Yaw Uploader] [Get yaw data] success, rate {self.speed_test['get_yaw_data']:.2f} ops/s")
            except Exception as e:
                log.error(f"      [Yaw Uploader] [Get yaw data] error: {e}")
            time.sleep(0.05)
        log.error("      [Yaw Uploader] [Get yaw data] exiting")

    def upload_yaw_data_to_local(self):
        log.info("      [Yaw Uploader] [Local yaw upload] starting...")
        while not self.stop_flag:
            try:
                if self.pre_data["send_local"][0] != self.yaw_data[0] and self.yaw_data[0]:
                    ut, resolve_data = self.yaw_data[0], self.yaw_data[1]
                    if resolve_data:
                        send_orientation(
                            url=self.local_url, time=ut, orientation=resolve_data, agent=self.agent
                        )
                    log.success(f"        [Yaw Uploader] [Local yaw upload] succeeded, rate {self.speed_test['get_local_yaw_data']:.2f} ops/s, yaw {resolve_data}m")
                    self.pre_data["send_local"] = [ut, resolve_data]
            except Exception as e:
                log.error(f"        [Yaw Uploader] [Local yaw upload] error {e}")
                time.sleep(1)
            time.sleep(0.05)
        log.error("      [Yaw Uploader] [Local yaw upload] exiting")

    def upload_yaw_data_to_remote(self):
        log.info("      [Yaw Uploader] [Remote yaw upload] starting...")
        while not self.stop_flag:
            try:
                if self.pre_data["send_remote"][0] != self.yaw_data[0] and self.yaw_data[0]:
                    ut, resolve_data = self.yaw_data[0], self.yaw_data[1]
                    if resolve_data:
                        send_orientation(
                            url=self.remote_url, time=ut, orientation=resolve_data, agent=self.agent
                        )
                    log.success(
                        f"        [Yaw Uploader] [Remote yaw upload] succeeded, rate {self.speed_test['get_remote_yaw_data']:.2f} ops/s, yaw {resolve_data}m")
                    self.pre_data["send_remote"] = [ut, resolve_data]
            except Exception as e:
                log.error(f"        [Yaw Uploader] [Remote yaw upload] error {e}")
                time.sleep(1)
            time.sleep(0.05)
        log.error("      [Yaw Uploader] [Remote yaw upload] exiting")

    def upload_yaw_data_to_db(self):
        log.info("      [Yaw Uploader] [DB yaw upload] starting...")
        while not self.stop_flag:
            try:
                if self.pre_data["send_db"][0] != self.yaw_data[0] and self.yaw_data[0]:
                    ut, resolve_data = self.yaw_data[0], self.yaw_data[1]
                    if resolve_data:
                        upload_orientation_data(ut, resolve_data, self.table_name, self.sql_config)
                    log.success(
                        f"        [Yaw Uploader] [DB yaw upload] succeeded, rate {self.speed_test['get_db_yaw_data']:.2f} ops/s, yaw {resolve_data}m")
                    self.pre_data["send_db"] = [ut, resolve_data]
            except Exception as e:
                log.error(f"        [Yaw Uploader] [DB yaw upload] error {e}")
                time.sleep(1)
            time.sleep(0.05)
        log.error("      [Yaw Uploader] [DB yaw upload] exiting")

    def stop(self):
        self.stop_flag = True
        log.info("  [Yaw Uploader] Stopping, waiting for tasks to finish...")
        for t in self.task_list:
            t.join()
        log.error("  [Yaw Uploader] Stopped, upload ended")


if __name__ == "__main__":
    import sys
    location_model = YawUploader(
        config_path=sys.argv[1], time_str=sys.argv[2], agent=sys.argv[3],
        remote_url=sys.argv[4], local_url=sys.argv[5]
    )
    log.success("  [Yaw Uploader] Started. Press any key to exit.. \n")
    input()
    location_model.stop()
    exit(3)
