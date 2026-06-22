from time import sleep

from Tools.ConfigUtils import read_config
from Tools.FileUtils import check_if_exist
from Tools.DBUtils import RedisDict
from Tools.LatLonTools import transform_to_xygen, check_distance, distance
import Tools.LogUtils as log
from Tools.TimeUtils import get_time_delta_from_str
from datetime import datetime
import os


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

    def clear_time_data(self):
        self.redis_dict["time_str"] = None
        self.redis_dict["photo_folder"] = None
        self.redis_dict["ugv_photo_folder"] = None
        self.redis_dict["uav_photo_table_name"] = None
        self.redis_dict["depart"] = False
        self.redis_dict["uav_longitude"] = -1
        self.redis_dict["uav_latitude"] = -1
        self.redis_dict["uav_location_time"] = None
        self.redis_dict["uav_height"] = None
        self.redis_dict["uav_height_time"] = None
        self.redis_dict["ugv_longitude"] = -1
        self.redis_dict["ugv_latitude"] = -1
        self.redis_dict["ugv_location_time"] = None
        self.redis_dict["ugv_height"] = None
        self.redis_dict["ugv_height_time"] = None
        self.redis_dict["uav_ugv_distance"] = -1

        self.redis_dict["uav_latest_photo"] = None
        self.redis_dict["uav_photo_time"] = None
        
        self.redis_dict["ugv_latest_photo"] = None
        self.redis_dict["ugv_photo_time"] = None

        self.redis_dict["origin_uav_height"] = -1
        self.redis_dict["origin_ugv_height"] = -1
        self.redis_dict["origin_latitude"] = -1
        self.redis_dict["origin_longitude"] = -1
        self.redis_dict["origin_time"] = None

        self.redis_dict["threshold"] = 2
        self.redis_dict["emergency_stop"] = False
        self.redis_dict["uav_current_pos"] = [None, None]
        self.redis_dict["ugv_current_pos"] = [None, None]
        self.redis_dict["D"] = None
        self.redis_dict["H"] = None
        self.redis_dict["DH_t"] = 0
        log.success(" [Remote Data Server] Cleared time ID successfully")

    def set_time_str(self, time_string):
        self.redis_dict["time_str"] = time_string
        self.redis_dict["photo_folder"] = f"{self.photo_path}/{time_string}_uav"
        self.redis_dict["ugv_photo_folder"] = f"{self.photo_path}/{time_string}_ugv"
        check_if_exist(self.redis_dict["photo_folder"])
        check_if_exist(self.redis_dict["ugv_photo_folder"])
        log.success(f" [Remote Data Server] Cached time {time_string} successfully")

    def set_ugv_position(self, latitude, longitude, time):
        self.redis_dict["ugv_latitude"] = latitude
        self.redis_dict["ugv_longitude"] = longitude
        self.redis_dict["ugv_location_time"] = time \
            if self.redis_dict["origin_latitude"] < 0 \
            else get_time_delta_from_str(str(self.redis_dict["origin_time"]), time)
        if self.redis_dict["origin_latitude"] >= 0:
            self.redis_dict["ugv_current_pos"] = transform_to_xygen(
                origin_latitude=self.redis_dict["origin_latitude"],
                origin_longitude=self.redis_dict["origin_longitude"],
                current_latitude=latitude, current_longitude=longitude
            )

    def set_ugv_height(self, height, time):
        self.redis_dict["ugv_height"] = height - self.redis_dict['origin_ugv_height']
        self.redis_dict["ugv_height_time"] = time \
            if self.redis_dict["origin_latitude"] < 0 \
            else get_time_delta_from_str(str(self.redis_dict["origin_time"]), time)

    def set_uav_upload_photo(self, file_path, time):
        self.redis_dict["uav_latest_photo"] = file_path
        self.redis_dict["uav_photo_time"] = time \
            if self.redis_dict["origin_latitude"] < 0 \
            else get_time_delta_from_str(str(self.redis_dict["origin_time"]), time)

    def set_ugv_upload_photo(self, file_path, time):
        self.redis_dict["ugv_latest_photo"] = file_path
        self.redis_dict["ugv_photo_time"] = time \
            if self.redis_dict["origin_latitude"] < 0 \
            else get_time_delta_from_str(str(self.redis_dict["origin_time"]), time)

    def set_uav_position(self, latitude, longitude, time):
        self.redis_dict["uav_latitude"] = latitude
        self.redis_dict["uav_longitude"] = longitude
        self.redis_dict["uav_location_time"] = time \
            if self.redis_dict["origin_latitude"] < 0 \
            else get_time_delta_from_str(str(self.redis_dict["origin_time"]), time)
        if self.redis_dict["origin_latitude"] >= 0:
            self.redis_dict["uav_current_pos"] = transform_to_xygen(
                origin_latitude=self.redis_dict["origin_latitude"],
                origin_longitude=self.redis_dict["origin_longitude"],
                current_latitude=latitude, current_longitude=longitude
            )
   
    def set_DH(self, D, H):
        self.redis_dict["D"], self.redis_dict["H"] = D, H
        self.redis_dict["DH_t"] = get_time_delta_from_str(str(self.redis_dict["origin_time"]), datetime.now())
   
    def set_uav_height(self, height, time):
        self.redis_dict["uav_height"] = height - self.redis_dict["origin_uav_height"]
        self.redis_dict["uav_height_time"] = time \
            if self.redis_dict["origin_latitude"] < 0 \
            else get_time_delta_from_str(str(self.redis_dict["origin_time"]), time)

    def set_uav_orientation(self, orientation, time):
        self.redis_dict["uav_orientation"] = orientation
        self.redis_dict["uav_orientation_time"] = time \
            if self.redis_dict["origin_latitude"] < 0 \
            else get_time_delta_from_str(str(self.redis_dict["origin_time"]), time)

    def set_ugv_orientation(self, orientation, time):
        self.redis_dict["ugv_orientation"] = orientation
        self.redis_dict["ugv_orientation_time"] = time \
            if self.redis_dict["origin_latitude"] < 0 \
            else get_time_delta_from_str(str(self.redis_dict["origin_time"]), time)
    
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
            self.redis_dict['origin_latitude'] = self.redis_dict['ugv_latitude']
            self.redis_dict['origin_longitude'] = self.redis_dict['ugv_longitude']
            self.redis_dict['origin_uav_height'] = self.redis_dict['uav_height']
            self.redis_dict['origin_ugv_height'] = self.redis_dict['ugv_height']
            self.redis_dict['origin_time'] = self.redis_dict['ugv_location_time']
            return True
        return False

    def set_threshold(self, threshold):
        self.redis_dict['threshold'] = threshold

    def set_emergency_stop(self):
        self.redis_dict['emergency_stop'] = True

    def set_depart(self):
        self.redis_dict['depart'] = True
    
    def set_land(self):
        self.redis_dict['depart'] = False
        
