import time
from Tools.RequestTools import send_photo, send_photo_path, send_ugv_photo
from Tools.PhotoUtils import take_picture, Camera, PiCamera
from Tools.TimeUtils import micro_time_file_name
import Tools.LogUtils as log
from Tools.ConfigUtils import read_config
import os
from Tools.FileUtils import check_if_exist
from threading import Thread
from Tools.UploadSpeedUtils import SpeedCaculator


class PhotoUploader:
    def __init__(self, time_str, config_path, agent, remote_url, local_url):
        try:
            log.info("  [Photo Uploader] Initializing..")
            self.speed_test = SpeedCaculator()
            config = read_config(os.path.abspath(config_path))

            self.remote_url = remote_url
            self.local_url = local_url
            self.agent = agent
            self.photo_port = config['VideoPort']

            self.time_str = time_str
            self.picture_path = os.path.abspath(config['PhotoPath'])

            self.picture_path = os.path.join(self.picture_path, time_str)

            check_if_exist(self.picture_path)
            self.cam = Camera(self.photo_port) if self.photo_port != "PI" else PiCamera()
            self.stop_flag = False
            self.pre_data = {"send_remote": [None, None], "send_local": [None, None]}
            self.photo_data = [None, None]
            self.task_list = []
            self.start_mission()
            log.success("  [Photo Uploader] Initialization complete")
        except Exception as e:
            log.error(f"  [Photo Uploader] Initialization failed; backend API may be unavailable, error {e}")
            exit(-1)

    def start_mission(self):
        log.info("    [Photo Uploader] Preparing to start upload tasks...")
        # self.task_list.append(Thread(target=self.take_photo))
        # if self.agent == "UAV":
        #     self.task_list.append(Thread(target=self.upload_photo_to_remote))
        # else:
        #     self.task_list.append(Thread(target=self.ugv_upload_photo_to_remote))
        if self.agent == "UAV":
            self.task_list.append(Thread(target=self.take_photo_and_upload_to_remote))
        else:
            self.task_list.append(Thread(target=self.ugv_take_photo_and_upload_to_remote))
        # self.task_list.append(Thread(target=self.upload_photo_to_local))
        for t in self.task_list:
            t.start()
        log.success("    [Photo Uploader] Upload tasks started")

    def take_photo_and_upload_to_remote(self):
        log.info("    [Photo Uploader] [Capture and upload] starting..")
        while not self.stop_flag:
            try:
                upload_time_str = micro_time_file_name()
                file_name = f"{upload_time_str}.jpg"
                path = f"{self.picture_path}/{file_name}"
                self.cam.take_picture(path)
                self.photo_data = [path, upload_time_str]
                log.success(f"      [Photo Uploader] [Capture and upload] photo captured, rate {self.speed_test['get_take_photo_data']:.2f} ops/s")
                send_photo(self.remote_url, path, upload_time_str)
                log.success(f"      [Photo Uploader] [Capture and upload] remote upload succeeded, rate {self.speed_test['get_remote_photo_data']:.2f} ops/s")
            except Exception as e:
                log.error(f"      [Photo Uploader] [Capture and upload] error, retrying: {e}")
                time.sleep(1)
            time.sleep(0.01)
        log.error("    [Photo Uploader] [Photo uploader] closing")
    
    def ugv_take_photo_and_upload_to_remote(self):
        log.info("    [Photo Uploader] [Capture and upload] starting..")
        while not self.stop_flag:
            try:
                upload_time_str = micro_time_file_name()
                file_name = f"{upload_time_str}.jpg"
                path = f"{self.picture_path}/{file_name}"
                self.cam.take_picture(path)
                self.photo_data = [path, upload_time_str]
                log.success(f"      [Photo Uploader] [Capture and upload] photo captured, rate {self.speed_test['get_take_photo_data']:.2f} ops/s")
                send_ugv_photo(self.remote_url, path, upload_time_str)
                log.success(f"      [Photo Uploader] [Capture and upload] remote upload succeeded, rate {self.speed_test['get_remote_photo_data']:.2f} ops/s")
            except Exception as e:
                log.error(f"      [Photo Uploader] [Capture and upload] error, retrying: {e}")
                time.sleep(1)
            time.sleep(0.01)
        log.error("    [Photo Uploader] [Photo uploader] closing")

    def take_photo(self):
        log.info("    [Photo Uploader] [Capture] starting..")
        while not self.stop_flag:
            try:
                upload_time_str = micro_time_file_name()
                file_name = f"{upload_time_str}.jpg"
                path = f"{self.picture_path}/{file_name}"
                self.cam.take_picture(path)
                self.photo_data = [path, upload_time_str]
                log.success(f"      [Photo Uploader] [Capture] succeeded, rate {self.speed_test['get_take_photo_data']:.2f} ops/s")
            except Exception as e:
                log.error(f"      [Photo Uploader] [Capture] error, retrying: {e}")
                time.sleep(1)
            time.sleep(0.5)
        log.error("    [Photo Uploader] [Photo uploader] closing")

    def upload_photo_to_remote(self):
        log.info("    [Photo Uploader] [Remote upload] starting..")
        while not self.stop_flag:
            try:
                if self.photo_data[0] and self.pre_data['send_remote'][1] != self.photo_data[1]:
                    path, upload_time_str = self.photo_data[0], self.photo_data[1]
                    send_photo(self.remote_url, path, upload_time_str)
                    log.success(f"      [Photo Uploader] [Remote upload] succeeded, rate {self.speed_test['get_remote_photo_data']:.2f} ops/s")
                    self.pre_data['send_remote'] = [path, upload_time_str]
                else:
                    time.sleep(1)
            except Exception as e:
                log.error(f"      [Photo Uploader] [Remote upload] error, retrying: {e}")
                time.sleep(1)
            time.sleep(0.01)
        log.error("    [Photo Uploader] [Remote upload] closing")

    def ugv_upload_photo_to_remote(self):
        log.info("    [Photo Uploader] [Remote upload] starting..")
        while not self.stop_flag:
            try:
                if self.photo_data[0] and self.pre_data['send_remote'][1] != self.photo_data[1]:
                    path, upload_time_str = self.photo_data[0], self.photo_data[1]
                    send_ugv_photo(self.remote_url, path, upload_time_str)
                    log.success(f"      [Photo Uploader] [Remote upload] succeeded, rate {self.speed_test['get_remote_photo_data']:.2f} ops/s")
                    self.pre_data['send_remote'] = [path, upload_time_str]
                else:
                    time.sleep(1)
            except Exception as e:
                log.error(f"      [Photo Uploader] [Remote upload] error, retrying: {e}")
                time.sleep(1)
            time.sleep(0.01)
        log.error("    [Photo Uploader] [Remote upload] closing")

    def upload_photo_to_local(self):
        log.info("    [Photo Uploader] [Local upload] starting..")
        while not self.stop_flag:
            try:
                if self.photo_data[0] and self.pre_data['send_local'][1] != self.photo_data[1]:
                    path, upload_time_str = self.photo_data[0], self.photo_data[1]
                    send_photo_path(self.local_url, path, upload_time_str)
                    log.success(f"      [Photo Uploader] [Local upload] succeeded, rate {self.speed_test['get_local_photo_data']:.2f} ops/s")
                    self.pre_data['send_local'] = [path, upload_time_str]
                else:
                    time.sleep(1)
            except Exception as e:
                log.error(f"      [Photo Uploader] [Local upload] error, retrying: {e}")
                time.sleep(1)
            time.sleep(0.05)
        log.error("    [Photo Uploader] [Local upload] closing")

    def quit(self):
        log.info("  [Photo Uploader] Stopping..")
        self.stop_flag = True
        for t in self.task_list:
            t.join()
        self.cam.release()
        log.error("  [Photo Uploader] Exited")


if __name__ == "__main__":
    import sys
    photo_model = PhotoUploader(
        config_path=sys.argv[1], time_str=sys.argv[2], agent=sys.argv[3],
        remote_url=sys.argv[4], local_url=sys.argv[5]
    )
    # photo_model = PhotoUploader(config_path="./Configs/PhotoUploadConfig.yaml", time_str="202408222322")
    log.success("  [Photo Uploader] Started. Press any key to exit...\n")
    input()
    photo_model.quit()
    exit(1)


