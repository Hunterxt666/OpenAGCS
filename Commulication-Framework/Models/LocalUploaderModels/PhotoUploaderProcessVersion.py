import time
from Tools.RequestTools import send_photo, send_photo_path, send_ugv_photo
from Tools.PhotoUtils import Camera, PiCamera
from Tools.TimeUtils import micro_time_file_name
import Tools.LogUtils as log
from Tools.DBUtils import RedisDict
from Tools.ConfigUtils import read_config
import os
from Tools.FileUtils import check_if_exist
from Tools.UploadSpeedUtils import SpeedCaculator


def take_pictures(config, time_str):
    redis_dict = RedisDict(
        host=config["RedisInfo"]["RedisIP"], port=config["RedisInfo"]["RedisPort"],
        db=config["RedisInfo"]["dbID"]
    )
    speed_test = SpeedCaculator()
    cam = Camera(config['VideoPort']) if config['VideoPort'] != "PI" else PiCamera()
    picture_path = os.path.abspath(config['PhotoPath'])
    picture_path = os.path.join(picture_path, time_str)
    check_if_exist(picture_path)
    while not redis_dict['stop_photo_process']:
        try:
            upload_time_str = micro_time_file_name()
            file_name = f"{upload_time_str}.jpg"
            path = f"{picture_path}/{file_name}"
            cam.take_picture(path)
            redis_dict['photo_data'] = [path, upload_time_str]
            log.success(f"      [Photo Uploader] Photo captured, rate {speed_test['get_take_photo_data']:.2f} ops/s")
        except Exception as e:
            log.error(f"      [Photo Uploader] Photo capture error {e}")
        time.sleep(0.01)


def upload_photo_to_remote(config, remote_url):
    redis_dict = RedisDict(
        host=config["RedisInfo"]["RedisIP"], port=config["RedisInfo"]["RedisPort"],
        db=config["RedisInfo"]["dbID"]
    )
    data = [None] * 2
    speed_test = SpeedCaculator()
    while not redis_dict['stop_photo_process']:
        try:
            cur_data = redis_dict['photo_data'][:]
            if cur_data[0] != data[0]:
                send_photo(remote_url, cur_data[0], cur_data[1])
                data = cur_data[:]
                log.success(f"      [Photo Uploader] Remote upload succeeded, rate {speed_test['remote_photo_data']:.2f} ops/s")
        except Exception as e:
            log.error(f"      [Photo Uploader] Error {e}")
        time.sleep(0.01)


def upload_ugv_photo_to_remote(config, remote_url):
    redis_dict = RedisDict(
        host=config["RedisInfo"]["RedisIP"], port=config["RedisInfo"]["RedisPort"],
        db=config["RedisInfo"]["dbID"]
    )
    data = [None] * 2
    speed_test = SpeedCaculator()
    while not redis_dict['stop_photo_process']:
        try:
            cur_data = redis_dict['photo_data'][:]
            if cur_data[0] != data[0]:
                send_ugv_photo(remote_url, cur_data[0], cur_data[1])
                data = cur_data[:]
                log.success(f"      [Photo Uploader] Remote upload succeeded, rate {speed_test['remote_photo_data']:.2f} ops/s")
        except Exception as e:
            log.error(f"      [Photo Uploader] Error {e}")
        time.sleep(0.01)


def upload_photo_to_local(config, local_url):
    redis_dict = RedisDict(
        host=config["RedisInfo"]["RedisIP"], port=config["RedisInfo"]["RedisPort"],
        db=config["RedisInfo"]["dbID"]
    )
    data = [None] * 2
    speed_test = SpeedCaculator()
    while not redis_dict['stop_photo_process']:
        try:
            cur_data = redis_dict['photo_data'][:]
            if cur_data[0] != data[0]:
                send_photo_path(local_url, cur_data[0], cur_data[1])
                data = cur_data[:]
                log.success(f"      [Photo Uploader] Local upload succeeded, rate {speed_test['local_photo_data']:.2f} ops/s")
        except Exception as e:
            log.error(f"      [Photo Uploader] Error {e}")
        time.sleep(0.01)


if __name__ == "__main__":
    import sys
    import multiprocessing
    config_path = sys.argv[1]
    timestr = sys.argv[2]
    remote = sys.argv[4]
    local = sys.argv[5]
    cfg = read_config(config_path)
    r_dict = RedisDict(
        host=cfg["RedisInfo"]["RedisIP"], port=cfg["RedisInfo"]["RedisPort"],
        db=cfg["RedisInfo"]["dbID"]
    )
    r_dict['stop_photo_process'] = False
    r_dict['photo_data'] = [None] * 2
    process = [
        multiprocessing.Process(target=take_pictures, args=(cfg, timestr)),
        multiprocessing.Process(target=upload_photo_to_local, args=(cfg, local)),
    ]
    if sys.argv[3] == "UAV":
        process.append(multiprocessing.Process(target=upload_photo_to_remote, args=(cfg, remote)))
    else:
        process.append(multiprocessing.Process(target=upload_ugv_photo_to_remote, args=(cfg, remote)))
    for p in process:
        p.start()
    log.success("  [Photo Uploader] Started. Press any key to exit...\n")
    input()
    r_dict['stop_photo_process'] = True
    for p in process:
        p.join()
    exit(1)