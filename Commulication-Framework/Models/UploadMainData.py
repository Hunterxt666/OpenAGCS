import threading
import time

from Tools.TimeUtils import time_file_name
from Tools.ConfigUtils import read_config
from Tools.FileUtils import check_if_exist, build_run_python_sh
from Tools.ProcessUtils import ensure_processes_survive_startup
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
        if len(self.scripts) != len(self.configs):
            raise ValueError(
                "Uploader scripts/configs must contain the same number of entries"
            )
        self.sh_path = os.path.abspath(config['sh_path'])
        check_if_exist(self.sh_path)
        self.p_num = len(self.configs)
        self.sh_paths = [f"{self.sh_path}/local_upload_{i}.sh" for i in range(self.p_num)]
        self.remote_url = config["RemoteURL"]
        self.local_url = config["LocalURL"]
        self.agent_type = config["AgentType"]
        self.process_startup_grace_seconds = float(
            config.get("ProcessStartupGraceSeconds", 0.5)
        )
        self.process = []
        self.origin_thread = None

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
                return False
            flag = False
            while not flag and self.flag_origin:
                log.info("  [Acquisition Main] UAV waiting to sync time with server")
                flag = send_time_str(self.remote_url, self.time_str)
                time.sleep(1)
        if not self.flag_origin or self.time_str is None:
            return False
        if not send_time_str(self.local_url, self.time_str):
            raise RuntimeError("Failed to set the active mission on the local API")
        log.success("  [Acquisition Main] Backend API check passed")
        self.generate_sh()
        try:
            for i in range(self.p_num):
                self.process.append(
                    subprocess.Popen(
                        ['/bin/bash', self.sh_paths[i]],
                        stdin=subprocess.PIPE,
                    )
                )
            ensure_processes_survive_startup(
                list(zip(self.sh_paths, self.process)),
                self.process_startup_grace_seconds,
            )
        except Exception:
            self.flag_origin = False
            self._terminate_started_processes()
            raise

        for sh_path in self.sh_paths:
            log.success(
                f" [Acquisition Main] Process {sh_path} "
                "started successfully"
            )
        return True

    def _terminate_started_processes(self):
        """Terminate partially started uploader children after startup failure."""
        for process in self.process:
            if process.poll() is None:
                process.terminate()
        for process in self.process:
            if process.poll() is None:
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.0)
            if process.stdin is not None:
                process.stdin.close()
        self.process = []

    def stop_process(self):
        self.flag_origin = False
        for i, process in enumerate(self.process):
            if process.poll() is not None or process.stdin is None:
                continue
            try:
                process.stdin.write("quit \n".encode('utf-8'))
                process.stdin.flush()
                log.warn(
                    " [Acquisition Main] Sent terminate signal to process "
                    f"{self.sh_paths[i]}"
                )
            except (BrokenPipeError, OSError) as error:
                log.warn(
                    f" [Acquisition Main] Process {self.sh_paths[i]} "
                    f"control pipe closed: {error}"
                )
        for i, process in enumerate(self.process):
            process.wait()
            log.error(
                f" [Acquisition Main] Process {self.sh_paths[i]} closed"
            )
        if self.agent_type == "UAV":
            send_clean_str(self.remote_url)
        send_clean_str(self.local_url)
        
    def start_upload(self):
        if self.agent_type == "UGV":
            origin_target = self.ugv_origin_pos
        else:
            origin_target = self.uav_origin_pos
        try:
            started = self.start_process()
        except Exception:
            self.flag_origin = False
            raise
        if started is False:
            return False
        self.origin_thread = threading.Thread(
            target=origin_target,
            name=f"{self.agent_type.lower()}-origin-sync",
            daemon=True,
        )
        self.origin_thread.start()
        return True
    
    
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
