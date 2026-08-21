from time import sleep

from Tools.ConfigUtils import read_config
from Tools.FileUtils import check_if_exist
from Tools.DBUtils import RedisDict
from Tools.LatLonTools import transform_to_xygen, check_distance, distance
import Tools.LogUtils as log
from Tools.TimeUtils import get_time_delta_from_str
from Tools.TelemetryUtils import derive_planar_velocity
from datetime import datetime
import os
import time


class RemoteServerData:
    def __init__(self, config_path):
        log.info(" [Remote Data Server] Initializing..")

        config = read_config(config_path)
        self.redis_dict = RedisDict(
            host=config["RedisInfo"]["RedisIP"], port=config["RedisInfo"]["RedisPort"],
            db=config["RedisInfo"]["dbID"]
        )
        self.photo_path = os.path.abspath(config['PhotoPath'])
        self.pre_clean = config['PreCleanPath']

    def _set_many(self, values, mission_id=None):
        set_many_if = getattr(self.redis_dict, "set_many_if", None)
        if mission_id is not None and set_many_if is not None:
            return set_many_if("time_str", mission_id, values)
        if mission_id is not None:
            active_mission = self.redis_dict["time_str"]
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
            "time_str": None,
            "photo_folder": None,
            "ugv_photo_folder": None,
            "uav_photo_table_name": None,
            "depart": False,
            "uav_longitude": -1,
            "uav_latitude": -1,
            "uav_location_time": None,
            "uav_height": None,
            "uav_height_time": None,
            "ugv_longitude": -1,
            "ugv_latitude": -1,
            "ugv_location_time": None,
            "ugv_velocity": [0.0, 0.0],
            "ugv_velocity_time": None,
            "ugv_height": None,
            "ugv_height_time": None,
            "uav_orientation": None,
            "uav_orientation_time": None,
            "ugv_orientation": None,
            "ugv_orientation_time": None,
            "uav_ugv_distance": -1,
            "uav_latest_photo": None,
            "uav_photo_time": None,
            "ugv_latest_photo": None,
            "ugv_photo_time": None,
            "origin_uav_height": -1,
            "origin_ugv_height": -1,
            "origin_latitude": -1,
            "origin_longitude": -1,
            "origin_time": None,
            "threshold": 2,
            "emergency_stop": False,
            "uav_current_pos": [None, None],
            "ugv_current_pos": [None, None],
            "D": None,
            "H": None,
            "DH_t": 0,
            "mission_phase": None,
            "mission_phase_time": None,
            "mission_controller_time": None,
            "mission_active_source": None,
            "mission_airborne": False,
        })
        log.success(" [Remote Data Server] Cleared time ID successfully")

    def set_time_str(self, time_string):
        photo_folder = f"{self.photo_path}/{time_string}_uav"
        ugv_photo_folder = f"{self.photo_path}/{time_string}_ugv"
        check_if_exist(photo_folder)
        check_if_exist(ugv_photo_folder)
        values = {
            "time_str": time_string,
            "photo_folder": photo_folder,
            "ugv_photo_folder": ugv_photo_folder,
        }
        previous_mission = self.redis_dict["time_str"]
        if (
            previous_mission is None
            or str(previous_mission) != str(time_string)
        ):
            values.update({
                "depart": False,
                "uav_longitude": -1,
                "uav_latitude": -1,
                "uav_location_time": None,
                "uav_current_pos": [None, None],
                "uav_height": None,
                "uav_height_time": None,
                "uav_orientation": None,
                "uav_orientation_time": None,
                "ugv_longitude": -1,
                "ugv_latitude": -1,
                "ugv_location_time": None,
                "ugv_velocity": [0.0, 0.0],
                "ugv_velocity_time": None,
                "ugv_current_pos": [None, None],
                "ugv_height": None,
                "ugv_height_time": None,
                "ugv_orientation": None,
                "ugv_orientation_time": None,
                "origin_uav_height": -1,
                "origin_ugv_height": -1,
                "origin_latitude": -1,
                "origin_longitude": -1,
                "origin_time": None,
                "emergency_stop": False,
                "mission_phase": "IDLE",
                "mission_phase_time": time.time(),
                "mission_controller_time": None,
                "mission_active_source": None,
                "mission_airborne": False,
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
                f" [Remote Data Server] Rejected stale time {time_string}"
            )
            return False
        log.success(f" [Remote Data Server] Cached time {time_string} successfully")
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

    def set_ugv_position(self, latitude, longitude, time, mission_id=None):
        origin_latitude = self.redis_dict["origin_latitude"]
        origin_longitude = self.redis_dict["origin_longitude"]
        origin_time = self.redis_dict["origin_time"]
        current_pos = self.redis_dict["ugv_current_pos"]
        previous_pos = current_pos
        try:
            previous_location_time = self.redis_dict["ugv_location_time"]
        except KeyError:
            previous_location_time = None
        location_time = (
            time
            if origin_latitude < 0
            else get_time_delta_from_str(str(origin_time), time)
        )
        if origin_latitude >= 0:
            current_pos = transform_to_xygen(
                origin_latitude=origin_latitude,
                origin_longitude=origin_longitude,
                current_latitude=latitude, current_longitude=longitude
            )
        velocity = derive_planar_velocity(
            previous_pos,
            previous_location_time,
            current_pos,
            location_time,
        )
        return self._set_many({
            "ugv_latitude": latitude,
            "ugv_longitude": longitude,
            "ugv_location_time": location_time,
            "ugv_current_pos": current_pos,
            "ugv_velocity": velocity,
            "ugv_velocity_time": location_time,
        }, mission_id=mission_id)

    def set_ugv_height(self, height, time, mission_id=None):
        height_time = time \
            if self.redis_dict["origin_latitude"] < 0 \
            else get_time_delta_from_str(str(self.redis_dict["origin_time"]), time)
        return self._set_many({
            "ugv_height": height - self.redis_dict['origin_ugv_height'],
            "ugv_height_time": height_time,
        }, mission_id=mission_id)

    def set_uav_upload_photo(self, file_path, time):
        photo_time = time \
            if self.redis_dict["origin_latitude"] < 0 \
            else get_time_delta_from_str(str(self.redis_dict["origin_time"]), time)
        self._set_many({
            "uav_latest_photo": file_path,
            "uav_photo_time": photo_time,
        })

    def set_ugv_upload_photo(self, file_path, time):
        photo_time = time \
            if self.redis_dict["origin_latitude"] < 0 \
            else get_time_delta_from_str(str(self.redis_dict["origin_time"]), time)
        self._set_many({
            "ugv_latest_photo": file_path,
            "ugv_photo_time": photo_time,
        })

    def set_uav_position(self, latitude, longitude, time, mission_id=None):
        origin_latitude = self.redis_dict["origin_latitude"]
        origin_longitude = self.redis_dict["origin_longitude"]
        origin_time = self.redis_dict["origin_time"]
        current_pos = self.redis_dict["uav_current_pos"]
        location_time = (
            time
            if origin_latitude < 0
            else get_time_delta_from_str(str(origin_time), time)
        )
        if origin_latitude >= 0:
            current_pos = transform_to_xygen(
                origin_latitude=origin_latitude,
                origin_longitude=origin_longitude,
                current_latitude=latitude, current_longitude=longitude
            )
        return self._set_many({
            "uav_latitude": latitude,
            "uav_longitude": longitude,
            "uav_location_time": location_time,
            "uav_current_pos": current_pos,
        }, mission_id=mission_id)
   
    def set_DH(self, D, H):
        origin_time = self.redis_dict["origin_time"]
        dh_time = (
            0
            if origin_time is None
            else get_time_delta_from_str(str(origin_time), datetime.now())
        )
        self._set_many({"D": D, "H": H, "DH_t": dh_time})
   
    def set_uav_height(self, height, time, mission_id=None):
        height_time = time \
            if self.redis_dict["origin_latitude"] < 0 \
            else get_time_delta_from_str(str(self.redis_dict["origin_time"]), time)
        return self._set_many({
            "uav_height": height - self.redis_dict["origin_uav_height"],
            "uav_height_time": height_time,
        }, mission_id=mission_id)

    def set_uav_orientation(
        self, orientation, time, mission_id=None
    ):
        orientation_time = time \
            if self.redis_dict["origin_latitude"] < 0 \
            else get_time_delta_from_str(str(self.redis_dict["origin_time"]), time)
        return self._set_many({
            "uav_orientation": orientation,
            "uav_orientation_time": orientation_time,
        }, mission_id=mission_id)

    def set_ugv_orientation(
        self, orientation, time, mission_id=None
    ):
        orientation_time = time \
            if self.redis_dict["origin_latitude"] < 0 \
            else get_time_delta_from_str(str(self.redis_dict["origin_time"]), time)
        return self._set_many({
            "ugv_orientation": orientation,
            "ugv_orientation_time": orientation_time,
        }, mission_id=mission_id)
    
    def get_distance(self):
        return distance(
            a_latitude=self.redis_dict["ugv_latitude"], a_longitude=self.redis_dict["ugv_longitude"],
            b_latitude=self.redis_dict["uav_latitude"], b_longitude=self.redis_dict["uav_longitude"]
        )

    def set_origin_pos(self):
        flag = (
            self.redis_dict["origin_latitude"] < 0 <= self.redis_dict["ugv_latitude"]
            and self.redis_dict["uav_latitude"] >= 0 and self.redis_dict["uav_height"] is not None
            and self.redis_dict["ugv_height"] is not None
        )
        self.redis_dict["uav_ugv_distance"] = distance(
            a_latitude=self.redis_dict["ugv_latitude"], a_longitude=self.redis_dict["ugv_longitude"],
            b_latitude=self.redis_dict["uav_latitude"], b_longitude=self.redis_dict["uav_longitude"]
        )
        if flag and check_distance(
            a_latitude=self.redis_dict["ugv_latitude"], a_longitude=self.redis_dict["ugv_longitude"],
            b_latitude=self.redis_dict["uav_latitude"], b_longitude=self.redis_dict["uav_longitude"],
            threshold=self.redis_dict["threshold"]
        ):
            self._set_many({
                'origin_latitude': self.redis_dict['ugv_latitude'],
                'origin_longitude': self.redis_dict['ugv_longitude'],
                'origin_uav_height': self.redis_dict['uav_height'],
                'origin_ugv_height': self.redis_dict['ugv_height'],
                'origin_time': self.redis_dict['ugv_location_time'],
            })
            return True
        return False

    def set_threshold(self, threshold):
        self.redis_dict['threshold'] = threshold

    def set_emergency_stop(self):
        self.redis_dict['emergency_stop'] = True

    def clear_emergency_stop(self):
        self.redis_dict['emergency_stop'] = False

    def set_depart(self):
        self.redis_dict['depart'] = True
    
    def set_land(self):
        self.redis_dict['depart'] = False

    def set_mission_state(
        self,
        mission_id,
        phase,
        active_source=None,
        airborne=None,
        controller_update=False,
    ):
        if airborne is None:
            airborne = bool(self.redis_dict["mission_airborne"])
        now = time.time()
        values = {
            "mission_phase": phase,
            "mission_phase_time": now,
            "mission_active_source": active_source,
            "mission_airborne": bool(airborne),
        }
        if controller_update:
            values["mission_controller_time"] = now
        return self._set_many(values, mission_id=mission_id)
