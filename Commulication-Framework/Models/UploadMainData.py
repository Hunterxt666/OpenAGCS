import threading
import time

from Tools.TimeUtils import time_file_name
from Tools.ConfigUtils import read_config
from Tools.FileUtils import check_if_exist, build_run_python_sh
from Tools.RequestTools import send_time_str, send_clean_str, get_time_str, set_origin_pos, get_origin_pos, set_local_origin_pos
import Tools.LogUtils as log
import subprocess
import os


class UploadMain:
    def __init__(self, config_path):
        self.time_str = time_file_name()
        self.flag_origin = True
        config = read_config(config_path)
        self.scripts = [os.path.abspath(x) for x in config['scripts']]
        self.configs = [os.path.abspath(x) for x in config['configs']]
        self.sh_path = os.path.abspath(config['sh_path'])
        check_if_exist(self.sh_path)
        self.p_num = len(self.configs)
        self.sh_paths = [f"{self.sh_path}/local_upload_{i}.sh" for i in range(self.p_num)]
        self.remote_url = config["RemoteURL"]
        self.local_url = config["LocalURL"]
        self.agent_type = config["AgentType"]
        self.process = []

    def uav_origin_pos(self):
        re = None
        while not re and self.flag_origin:
            re = set_origin_pos(self.remote_url)
            time.sleep(1)
            log.info("  [Acquisition Main] UAV querying origin...")
        if self.flag_origin:
            set_local_origin_pos(
                self.local_url, latitude=re["latitude"], longitude=re["longitude"], height=re["uav_height"],
                time=re["time"]
            )
        log.info("  [Acquisition Main] UAV origin set successfully")

    def ugv_origin_pos(self):
        re = None
        while not re and self.flag_origin:
            re = get_origin_pos(self.remote_url)
            time.sleep(1)
            log.info("  [Acquisition Main] UGV querying origin...")
        if self.flag_origin:
            set_local_origin_pos(
                self.local_url, latitude=re["latitude"], longitude=re["longitude"], height=re["ugv_height"], time=re["time"]
            )
        log.info("  [Acquisition Main] UGV origin set successfully")

    def generate_sh(self):
        for i in range(self.p_num):
            build_run_python_sh(
                self.sh_paths[i],
                [self.scripts[i], self.configs[i], self.time_str, self.agent_type, self.remote_url, self.local_url]
            )
            log.success(f" [Acquisition Main] Process file {self.sh_paths[i]} created")

    def start_process(self):
        if self.agent_type == "UGV":
            log.info("  [Acquisition Main] UGV waiting for UAV data refresh")
            self.time_str = None
            while self.time_str is None and self.flag_origin:
                try:
                    re = get_time_str(self.remote_url)
                    if re is not None:
                        self.time_str = re["time_str"]
                except Exception as e:
                    log.warn(f"  [Acquisition Main] UGV wait for UAV data refresh error {e}")
                time.sleep(1)
        else:
            if not self.flag_origin:
                return
            flag = False
            while not flag and self.flag_origin:
                log.info("  [Acquisition Main] UAV waiting to sync time with server")
                flag = send_time_str(self.remote_url, self.time_str)
                time.sleep(1)
        send_time_str(self.local_url, self.time_str)
        log.success("  [Acquisition Main] Backend API check passed")
        for i in range(self.p_num):
            self.process.append(subprocess.Popen(['/bin/bash', self.sh_paths[i]], stdin=subprocess.PIPE))
            log.success(f" [Acquisition Main] Process {self.sh_paths[i]} started successfully")

    def stop_process(self):
        self.flag_origin = False
        for i in range(self.p_num):
            self.process[i].stdin.write("quit \n".encode('utf-8'))
            self.process[i].stdin.flush()
            log.warn(f" [Acquisition Main] Sent terminate signal to process {self.sh_paths[i]}")
        for i in range(self.p_num):
            self.process[i].communicate()
            log.error(f" [Acquisition Main] Process {self.sh_paths[i]} closed")
        if self.agent_type == "UAV":
            send_clean_str(self.remote_url)
        send_clean_str(self.local_url)
        
    def start_upload(self):
        if self.agent_type == "UGV":
            threading.Thread(target=self.ugv_origin_pos).start()
        else:
            threading.Thread(target=self.uav_origin_pos).start()
        self.generate_sh()
        self.start_process()
    
    
if __name__ == "__main__":
    import sys
    upload_main = UploadMain(
        config_path=sys.argv[1],
    )
    upload_main.start_upload() 
    log.success(" [Acquisition Main] Started. Press any key to exit.. \n")
    input()
    upload_main.stop_process()
    exit(0)
