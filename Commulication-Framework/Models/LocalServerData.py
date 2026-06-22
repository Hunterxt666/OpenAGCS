import subprocess

from Tools.ConfigUtils import read_config
from Tools.LatLonTools import transform_to_xygen, distance
import Tools.LogUtils as log
from Tools.TimeUtils import get_time_delta_from_str, micro_time_file_name
from Tools.DBUtils import RedisDict


class LocalServerData:
    def __init__(self, config_path):
        log.info(" [Local Data Server] Initializing..")
        config = read_config(config_path)
        self.redis_dict = RedisDict(
            host=config["RedisInfo"]["RedisIP"], port=config["RedisInfo"]["RedisPort"],
            db=config["RedisInfo"]["dbID"]
        )
        self.photo_path = config['PhotoPath']
        self.sh_path = config['MainUploadPath']
        self.start_sh_path = config['ShPath']
        self.local_url = config["LocalUrl"]
        self.process = None

    def clear_time_data(self):
        self.redis_dict['time_str'] = None
        self.redis_dict['longitude'] = -1
        self.redis_dict['latitude'] = -1
        self.redis_dict['longitude_pre'] = -1
        self.redis_dict['latitude_pre'] = -1
        self.redis_dict['origin_longitude'] = -1
        self.redis_dict['origin_latitude'] = -1
        self.redis_dict['origin_height'] = -1
        self.redis_dict['origin_time'] = None
        self.redis_dict['yaw'] = None
        self.redis_dict['yaw_time'] = None
        self.redis_dict['cumulative_distance'] = -1
        self.redis_dict['xy'] = [None, None]
        self.redis_dict['location_time'] = None
        self.redis_dict['height'] = None
        self.redis_dict['control_input'] = [0]*4
        self.redis_dict['control_cmd'] = ""
        self.redis_dict['height_time'] = None
        self.redis_dict['latest_photo'] = None
        self.redis_dict['photo_time '] = None
        self.redis_dict['control_time'] = None
        self.redis_dict['lora_data'] = {}
        self.redis_dict['cmd_time'] = None
        log.success(" [Local Data Server] Cleared time ID successfully")

    def set_time_str(self, time_string):
        self.redis_dict['time_str'] = time_string
        log.success(f" [Local Data Server] Cached time {time_string} successfully")

    def set_position(self, latitude, longitude, time):
        if self.redis_dict['origin_latitude'] >= 0:
            self.redis_dict['xy'] = transform_to_xygen(
                origin_latitude=self.redis_dict['origin_latitude'], origin_longitude=self.redis_dict['origin_longitude'],
                current_longitude=longitude, current_latitude=latitude
            )

        self.redis_dict['latitude'] = latitude
        self.redis_dict['longitude'] = longitude
        if self.redis_dict['latitude_pre'] > 0:
            self.redis_dict['cumulative_distance'] = self.redis_dict['cumulative_distance'] + distance(
                self.redis_dict['latitude'], self.redis_dict['longitude'],
                self.redis_dict['latitude_pre'], self.redis_dict['longitude_pre']
            )
        self.redis_dict['latitude_pre'] = latitude
        self.redis_dict['longitude_pre'] = longitude
        self.redis_dict['location_time'] = time \
            if self.redis_dict['origin_latitude'] < 0 \
            else get_time_delta_from_str(str(self.redis_dict['origin_time']), time)

    def set_origin(self, origin_latitude, origin_longitude, origin_height, origin_time):
        self.redis_dict['origin_longitude'] = origin_longitude
        self.redis_dict['origin_latitude'] = origin_latitude
        self.redis_dict['origin_height'] = origin_height
        self.redis_dict['origin_time'] = origin_time
        self.redis_dict['cumulative_distance'] = 0

    def set_height(self, height, time):
        self.redis_dict['height'] = height - self.redis_dict['origin_height']
        self.redis_dict['height_time'] = time \
            if self.redis_dict['origin_latitude'] < 0 \
            else get_time_delta_from_str(str(self.redis_dict['origin_time']), time)

    def set_photo(self, path, time):
        self.redis_dict['latest_photo'] = path
        self.redis_dict['photo_time'] = time \
            if self.redis_dict['origin_latitude'] < 0 \
            else get_time_delta_from_str(str(self.redis_dict['origin_time']), time)

    def run_upload_main(self):
        self.process = subprocess.Popen(['/bin/bash', self.sh_path], stdin=subprocess.PIPE)

    def start_upload(self):
        if not self.redis_dict['started']:
            self.redis_dict['started'] = True
            if self.process:
                try:
                    self.process.communicate()
                except Exception as e:
                        log.error(f"   [Local Data Server] Failed to interrupt existing script (may already be closed), error {e}")
            self.run_upload_main()
            log.success("   [Local Data Server] Process script started successfully")
        else:
            log.warn("   [Local Data Server] Already started")

    def stop_upload(self):
        self.process.stdin.write("quit \n".encode('utf-8'))
        self.process.stdin.flush()

    def end_upload(self):
        if self.redis_dict['started'] and self.process:
            self.stop_upload()
            log.error("     [Local Data Server] Data collection process stopped successfully")
            log.error("    [Local Data Server] Exiting")
            self.redis_dict['started'] = False
        else:
            log.warn("   [Local Data Server] Not started")

    def set_uav_control_input(self, x, y, z, yaw):
        self.redis_dict['control_input'] = [x, y, z, yaw]
        time = micro_time_file_name()
        self.redis_dict['control_time'] = time \
            if self.redis_dict['origin_latitude'] < 0 \
            else get_time_delta_from_str(str(self.redis_dict['origin_time']), time)

    def set_uav_control_cmd(self, cmd):
        self.redis_dict['control_cmd'] = cmd
        time = micro_time_file_name()
        self.redis_dict['cmd_time'] = time \
            if self.redis_dict['origin_latitude'] < 0 \
            else get_time_delta_from_str(str(self.redis_dict['origin_time']), time)

    def set_yaw(self, yaw, time):
        self.redis_dict['yaw'] = yaw
        self.redis_dict['yaw_time'] = time \
            if self.redis_dict['origin_latitude'] < 0 \
            else get_time_delta_from_str(str(self.redis_dict['origin_time']), time)
