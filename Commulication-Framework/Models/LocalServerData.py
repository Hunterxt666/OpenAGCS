import os
import subprocess
import sys
import time

from Tools.ConfigUtils import read_config
from Tools.LatLonTools import transform_to_xygen, distance
import Tools.LogUtils as log
from Tools.TimeUtils import get_time_delta_from_str, micro_time_file_name
from Tools.DBUtils import RedisDict
from Tools.ProcessUtils import ensure_processes_survive_startup
from Tools.TelemetryUtils import derive_planar_velocity


class LocalServerData:
    def __init__(self, config_path):
        log.info(" [Local Data Server] Initializing..")
        config = read_config(config_path)
        self.redis_dict = RedisDict(
            host=config["RedisInfo"]["RedisIP"], port=config["RedisInfo"]["RedisPort"],
            db=config["RedisInfo"]["dbID"]
        )
        self.photo_path = config['PhotoPath']
        self.sh_path = os.path.abspath(config['MainUploadPath'])
        self.upload_config = os.path.abspath(
            config.get(
                'MainUploadConfig',
                './Configs/UploadMainConfig.yaml',
            )
        )
        self.start_sh_path = config['ShPath']
        self.local_url = config["LocalUrl"]
        self.process_startup_grace_seconds = float(
            config.get("ProcessStartupGraceSeconds", 2.0)
        )
        self.process = None

    def _set_many(self, values, mission_id=None):
        set_many_if = getattr(self.redis_dict, "set_many_if", None)
        if mission_id is not None and set_many_if is not None:
            return set_many_if("time_str", mission_id, values)
        if mission_id is not None:
            active_mission = self.redis_dict['time_str']
            if str(active_mission) != str(mission_id):
                return False
        set_many = getattr(self.redis_dict, "set_many", None)
        if set_many is not None:
            set_many(values)
            return True
        for key, value in values.items():
            self.redis_dict[key] = value
        return True

    def clear_time_data(self):
        self._set_many({
            'time_str': None,
            'longitude': -1,
            'latitude': -1,
            'longitude_pre': -1,
            'latitude_pre': -1,
            'origin_longitude': -1,
            'origin_latitude': -1,
            'origin_height': -1,
            'origin_time': None,
            'yaw': None,
            'yaw_time': None,
            'cumulative_distance': -1,
            'xy': [None, None],
            'location_time': None,
            'velocity': [0.0, 0.0],
            'velocity_time': None,
            'height': None,
            'control_input': [0] * 4,
            'control_cmd': "",
            'height_time': None,
            'latest_photo': None,
            'photo_time': None,
            'control_time': None,
            'lora_data': {},
            'lora_received_at': {},
            'emergency_stop': False,
            'cmd_time': None,
        })
        log.success(" [Local Data Server] Cleared time ID successfully")

    def set_time_str(self, time_string):
        previous_mission = self.redis_dict['time_str']
        values = {'time_str': time_string}
        if (
            previous_mission is None
            or str(previous_mission) != str(time_string)
        ):
            values.update({
                'longitude': -1,
                'latitude': -1,
                'longitude_pre': -1,
                'latitude_pre': -1,
                'origin_longitude': -1,
                'origin_latitude': -1,
                'origin_height': -1,
                'origin_time': None,
                'cumulative_distance': -1,
                'xy': [None, None],
                'location_time': None,
                'velocity': [0.0, 0.0],
                'velocity_time': None,
                'yaw': None,
                'yaw_time': None,
                'height': None,
                'height_time': None,
                'control_input': [0] * 4,
                'control_cmd': "",
                'control_time': None,
                'cmd_time': None,
                'lora_data': {},
                'lora_received_at': {},
                'emergency_stop': False,
            })
        set_if_newer = getattr(
            self.redis_dict, "set_many_if_newer", None
        )
        if set_if_newer is not None:
            stored = set_if_newer("time_str", time_string, values)
        else:
            stored = self._is_non_regressing_mission(
                previous_mission, time_string
            )
            if stored:
                self._set_many(values)
        if not stored:
            log.warn(
                f" [Local Data Server] Rejected stale time {time_string}"
            )
            return False
        log.success(f" [Local Data Server] Cached time {time_string} successfully")
        return True

    @staticmethod
    def _is_non_regressing_mission(current, candidate):
        if current is None or str(current) in {"", "null"}:
            return True
        current = str(current)
        candidate = str(candidate)
        if current == candidate:
            return True
        if not current.isdigit() or not candidate.isdigit():
            return False
        return (len(candidate), candidate) >= (len(current), current)

    def set_position(self, latitude, longitude, time, mission_id=None):
        origin_latitude = self.redis_dict['origin_latitude']
        origin_longitude = self.redis_dict['origin_longitude']
        origin_time = self.redis_dict['origin_time']
        previous_latitude = self.redis_dict['latitude_pre']
        previous_longitude = self.redis_dict['longitude_pre']
        cumulative_distance = self.redis_dict['cumulative_distance']
        xy = self.redis_dict['xy']
        previous_xy = xy
        try:
            previous_location_time = self.redis_dict['location_time']
        except KeyError:
            previous_location_time = None
        if origin_latitude >= 0:
            xy = transform_to_xygen(
                origin_latitude=origin_latitude, origin_longitude=origin_longitude,
                current_longitude=longitude, current_latitude=latitude
            )

        if previous_latitude > 0:
            cumulative_distance = cumulative_distance + distance(
                latitude, longitude, previous_latitude, previous_longitude
            )
        location_time = (
            time
            if origin_latitude < 0
            else get_time_delta_from_str(str(origin_time), time)
        )
        velocity = derive_planar_velocity(
            previous_xy,
            previous_location_time,
            xy,
            location_time,
        )
        return self._set_many({
            'latitude': latitude,
            'longitude': longitude,
            'latitude_pre': latitude,
            'longitude_pre': longitude,
            'cumulative_distance': cumulative_distance,
            'xy': xy,
            'location_time': location_time,
            'velocity': velocity,
            'velocity_time': location_time,
        }, mission_id=mission_id)

    def set_origin(self, origin_latitude, origin_longitude, origin_height, origin_time):
        self._set_many({
            'origin_longitude': origin_longitude,
            'origin_latitude': origin_latitude,
            'origin_height': origin_height,
            'origin_time': origin_time,
            'cumulative_distance': 0,
        })

    def set_height(self, height, time, mission_id=None):
        origin_height = self.redis_dict['origin_height']
        origin_latitude = self.redis_dict['origin_latitude']
        origin_time = self.redis_dict['origin_time']
        height_time = (
            time
            if origin_latitude < 0
            else get_time_delta_from_str(str(origin_time), time)
        )
        return self._set_many({
            'height': height - origin_height,
            'height_time': height_time,
        }, mission_id=mission_id)

    def set_photo(self, path, time):
        photo_time = time \
            if self.redis_dict['origin_latitude'] < 0 \
            else get_time_delta_from_str(str(self.redis_dict['origin_time']), time)
        self._set_many({'latest_photo': path, 'photo_time': photo_time})

    def run_upload_main(self):
        child_environment = os.environ.copy()
        child_environment["AGCS_PYTHON_EXECUTABLE"] = sys.executable
        process = subprocess.Popen(
            ['/bin/bash', self.sh_path, self.upload_config],
            stdin=subprocess.PIPE,
            env=child_environment,
        )
        try:
            ensure_processes_survive_startup(
                [("main uploader", process)],
                self.process_startup_grace_seconds,
            )
        except Exception:
            if process.stdin is not None:
                process.stdin.close()
            self.process = None
            raise
        self.process = process
        return process

    def start_upload(self):
        if self.redis_dict['started']:
            log.warn("   [Local Data Server] Already started")
            return False

        if self.process is not None and self.process.poll() is None:
            raise RuntimeError(
                "A previous main uploader process is still running"
            )

        self.process = None
        self.redis_dict['started'] = False
        try:
            self.run_upload_main()
        except Exception:
            self.redis_dict['started'] = False
            self.process = None
            raise

        self.redis_dict['started'] = True
        log.success(
            "   [Local Data Server] Process script started successfully"
        )
        return True

    def stop_upload(self):
        if self.process is None or self.process.poll() is not None:
            return False
        if self.process.stdin is None:
            raise RuntimeError("Main uploader process has no control pipe")
        self.process.stdin.write("quit \n".encode('utf-8'))
        self.process.stdin.flush()
        return True

    def end_upload(self):
        if self.redis_dict['started'] and self.process:
            stop_requested = self.stop_upload()
            if stop_requested:
                log.error(
                    "     [Local Data Server] Data collection stop requested"
                )
            else:
                log.warn(
                    "     [Local Data Server] Data collection process "
                    "had already exited"
                )
            log.error("    [Local Data Server] Exiting")
            self.redis_dict['started'] = False
            return stop_requested
        else:
            log.warn("   [Local Data Server] Not started")
            return False

    def set_uav_control_input(self, x, y, z, yaw):
        time = micro_time_file_name()
        control_time = time \
            if self.redis_dict['origin_latitude'] < 0 \
            else get_time_delta_from_str(str(self.redis_dict['origin_time']), time)
        self._set_many({
            'control_input': [x, y, z, yaw],
            'control_time': control_time,
        })

    def set_uav_control_cmd(self, cmd):
        time = micro_time_file_name()
        cmd_time = time \
            if self.redis_dict['origin_latitude'] < 0 \
            else get_time_delta_from_str(str(self.redis_dict['origin_time']), time)
        self._set_many({'control_cmd': cmd, 'cmd_time': cmd_time})

    def set_yaw(self, yaw, time, mission_id=None):
        yaw_time = time \
            if self.redis_dict['origin_latitude'] < 0 \
            else get_time_delta_from_str(str(self.redis_dict['origin_time']), time)
        return self._set_many(
            {'yaw': yaw, 'yaw_time': yaw_time},
            mission_id=mission_id,
        )

    def set_lora_data(self, data_type, data, received_at=None):
        lora_data = dict(self.redis_dict['lora_data'] or {})
        received_times = dict(self.redis_dict['lora_received_at'] or {})
        lora_data[data_type] = data
        received_times[data_type] = (
            time.time() if received_at is None else float(received_at)
        )
        self._set_many({
            'lora_data': lora_data,
            'lora_received_at': received_times,
        })

    def set_emergency_stop(self, enabled=True):
        self.redis_dict['emergency_stop'] = bool(enabled)
