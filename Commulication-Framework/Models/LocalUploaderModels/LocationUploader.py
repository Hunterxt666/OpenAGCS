from Tools.ConfigUtils import read_config
import serial
import socket
import time
import copy
import Tools.LogUtils as log
from Tools.DBUtils import create_rtk_data_table, upload_rtk_data
import base64
from Tools.ResolveDataUtils import resolve_gga_data
from threading import Thread
from Tools.UploadSpeedUtils import SpeedCaculator
from Tools.RequestTools import send_pos


class LocationUploader:
    def __init__(self, time_str, config_path, agent, remote_url, local_url):
        log.info("  [RTK Location Uploader] Initializing..")
        self.agent = agent
        self.remote_url = remote_url
        self.local_url = local_url
        self.pre_data = {"send_remote": None, "send_local": None, "send_db": None, "send_rtk": None}
        config = read_config(config_path)
        self.speed_test = SpeedCaculator()
        log.info("    [RTK Location Uploader] Initializing GGA module serial port..")
        self.serial = serial.Serial(config["SerialConfig"]["port"], config["SerialConfig"]["rate"]) 
        self.serial.reset_input_buffer()
        log.success("    [RTK Location Uploader] GGA module serial port connected")
        self.ntrip_config = config["NTRIPConfig"]
        self.sock = self.init_ntrip_connect()
        self.gga_string = [None, None]
        # self.table_name = f"{time_str}_{agent}_rkt_data"
        # self.sql_config = config['DBconfig']
        # log.info(f"    [RTK Location Uploader] Initializing SQL, creating RTK data table {self.table_name}..")
        # create_rtk_data_table(self.table_name, self.sql_config)
        # log.success(f"    [RTK Location Uploader] SQL initialized, RTK data table {self.table_name} created")
        self.stop_flag = False
        self.task_list = []
        self.start_mission()
        log.success("  [RTK Location Uploader] Initialization complete, starting upload")

    def init_ntrip_connect(self):
        try:
            log.info("    [RTK Location Uploader] Initializing RTK differential platform connection...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.ntrip_config["NTRIP_IP"], self.ntrip_config["NTRIP_PORT"]))
            log.success(f"      [RTK Location Uploader] RTK differential platform connection test succeeded ({self.ntrip_config['NTRIP_IP']}:{self.ntrip_config['NTRIP_PORT']})")
            log.info("      [RTK Location Uploader] Performing differential login")
            authorization = f"{self.ntrip_config['NTRIP_USERNAME']}:{self.ntrip_config['NTRIP_PASSWORD']}"
            authorization = base64.b64encode(authorization.encode()).decode()
            request_head = f"""GET /{self.ntrip_config['NTRIP_MOUNT_POINT']} HTTP/1.0\r\nUser-Agent: MOZIHAO-GNSS\r\nAccept: */*\r\nConnection: close\r\nAuthorization: Basic {authorization}\r\n\r\n"""
            sock.send(request_head.encode())
            response = sock.recv(1024)
            if "ICY 200 OK" not in response.decode():
                log.error("      [RTK Location Uploader] Differential login failed: invalid username/password")
                return None
            log.success("      [RTK Location Uploader] Differential login succeeded")
            return sock
        except Exception as e:
            log.error(f"      [RTK Location Uploader] Differential login failed; server unreachable or mode error, error {e}")
            return None

    def start_mission(self):
        log.info("    [RTK Location Uploader] Preparing to start upload tasks...")
        self.task_list.append(Thread(target=self.get_gngga))
        self.task_list.append(Thread(target=self.upload_location_data_to_local))
        self.task_list.append(Thread(target=self.upload_location_data_to_remote))
        # self.task_list.append(Thread(target=self.upload_location_data_to_db))
        if self.sock:
            self.task_list.append(Thread(target=self.upload_ntrip_data_to_node))
        else:
            log.error("    [RTK Location Uploader] Differential platform connection error; upload disabled")
        for t in self.task_list:
            t.start()
        log.success("    [RTK Location Uploader] Upload tasks started")

    def upload_ntrip_data_to_node(self):
        log.info("      [RTK Location Uploader] [Differential comms] starting...")
        while not self.stop_flag:
            try:
                if self.gga_string[0] and self.gga_string[0] != self.pre_data["send_rtk"]:
                    data = self.gga_string[0] + ""
                    self.sock.send(data.encode())
                    response = self.sock.recv(4096)
                    self.serial.write(response)
                    log.success("        [RTK Location Uploader] [Differential comms] response written successfully")
                    self.pre_data["send_rtk"] = data
            except Exception as e:
                log.error(f"        [RTK Location Uploader] [Differential comms] error writing NTRIP response {e}")
                self.sock = None
                while not self.stop_flag and not self.sock:
                    self.sock = self.init_ntrip_connect()
                    time.sleep(5)
            time.sleep(1)
        log.error("      [RTK Location Uploader] [Differential comms] exiting")

    def get_gngga(self):
        log.info("      [RTK Location Uploader] [Get GNGGA] starting...")
        while not self.stop_flag:
            try:
                line = self.serial.readline().decode('utf-8')
                # print(f"[raw data]{line}")
                if line.find('$GNGGA') != -1:
                    if line.split(',')[3] == 'N':
                        resolve_data = resolve_gga_data(line)
                        if resolve_data:
                            self.gga_string = [line, resolve_data]
                        log.success(f"      [RTK Location Uploader] [Get GNGGA] GNGGA refreshed, rate {self.speed_test['get_data']:.2f} ops/s")
            except Exception as e:
                log.error(f"      [RTK Location Uploader] [Get GNGGA] error: {e}")
                time.sleep(1)
            time.sleep(0.001)
        log.error("      [RTK Location Uploader] [Get GNGGA] exiting")

    def upload_location_data_to_local(self):
        log.info("      [RTK Location Uploader] [Local position upload] starting...")
        while not self.stop_flag:
            try:
                if self.gga_string[0] and self.gga_string[1]['locate_time'] != self.pre_data["send_local"]:
                    resolve_data = copy.deepcopy(self.gga_string[1])
                    if resolve_data:
                        send_pos(
                            url=self.local_url, longitude=resolve_data['longitude'], latitude=resolve_data['latitude'],
                            time=resolve_data['locate_time'], agent=self.agent
                        )
                        log.success(f"        [RTK Location Uploader] [Local position upload] succeeded, rate {self.speed_test['get_local_data']:.2f} ops/s, mode {resolve_data['mode']}, sats {resolve_data['star_num']}")
                        self.pre_data["send_local"] = resolve_data['locate_time']
            except Exception as e:
                log.error(f"        [RTK Location Uploader] [Local position upload] error {e}")
                time.sleep(1)
            time.sleep(0.05)
        log.error("      [RTK Location Uploader] [Local position upload] exiting")

    def upload_location_data_to_remote(self):
        log.info("      [RTK Location Uploader] [Remote position upload] starting...")
        while not self.stop_flag:
            try:
                if self.gga_string[0] and self.gga_string[1]['locate_time'] != self.pre_data["send_remote"]:
                    resolve_data = copy.deepcopy(self.gga_string[1])
                    if resolve_data:
                        send_pos(
                            url=self.remote_url, longitude=resolve_data['longitude'], latitude=resolve_data['latitude'],
                            time=resolve_data['locate_time'], agent=self.agent
                        )
                        # upload_rtk_data(resolve_data, self.table_name, self.sql_config)
                        log.success(f"        [RTK Location Uploader] [Remote position upload] succeeded, rate {self.speed_test['get_remote_data']:.2f} ops/s, mode {resolve_data['mode']}, sats {resolve_data['star_num']}")
                        self.pre_data["send_remote"] = resolve_data['locate_time']
            except Exception as e:
                log.error(f"        [RTK Location Uploader] [Remote position upload] error {e}")
                time.sleep(1)
            time.sleep(0.05)
        log.error("      [RTK Location Uploader] [Remote position upload] exiting")

    def upload_location_data_to_db(self):
        log.info("      [RTK Location Uploader] [DB position upload] starting...")
        while not self.stop_flag:
            try:
                if self.gga_string[0] and self.gga_string[1]['locate_time'] != self.pre_data["send_db"]:
                    resolve_data = copy.deepcopy(self.gga_string[1])
                    if resolve_data:
                        upload_rtk_data(resolve_data, self.table_name, self.sql_config)
                        log.success(f"        [RTK Location Uploader] [DB position upload] succeeded, rate {self.speed_test['get_db_data']:.2f} ops/s, mode {resolve_data['mode']}, sats {resolve_data['star_num']}")
                        self.pre_data["send_db"] = resolve_data['locate_time']
            except Exception as e:
                log.error(f"        [RTK Location Uploader] [DB position upload] error {e}")
                time.sleep(1)
            time.sleep(0.05)
        log.error("      [RTK Location Uploader] [DB position upload] exiting")

    def stop(self):
        self.stop_flag = True
        log.info("  [RTK Location Uploader] Stopping, waiting for tasks to finish...")
        for t in self.task_list:
            t.join()
        log.error("  [RTK Location Uploader] Stopped, upload ended")


if __name__ == "__main__":
    import sys
    location_model = LocationUploader(
        config_path=sys.argv[1], time_str=sys.argv[2], agent=sys.argv[3],
        remote_url=sys.argv[4], local_url=sys.argv[5]
    )
    log.success("  [RTK Location Uploader] Started. Press any key to exit.. \n")
    input()
    location_model.stop()
    exit(2)
