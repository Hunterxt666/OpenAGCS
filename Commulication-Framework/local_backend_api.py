"""Edge-side FastAPI service for the local node in the cooperative system.

The local backend is the control-facing API used by onboard components. It
stores the freshest UAV-side state and exposes the command/data endpoints that
the controller consumes during follow and return tasks.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import os
from Models.LocalServerData import LocalServerData
import Tools.LogUtils as log
from typing import Optional

from Models.ServerMesegeJsonModel import LoraItem

server_data: Optional[LocalServerData] = None

app = FastAPI()


@app.on_event("startup")
async def at_start_up():
    global server_data
    server_data = LocalServerData("Configs/LocalServerConfigs.yaml")
    log.success("[Backend API] Started successfully...")
    # server_data.start_upload()
    # log.success("  [Backend API] Auto-start upload task")


@app.on_event("shutdown")
async def at_shut_down():
    server_data.end_upload()
    log.error("[Backend API] Shutting down")


@app.get("/alive")
async def check_alive():
    log.success("  [Backend API] Health check called")
    return {"msg": "I am alive!!"}


@app.get("/curTimeStr")
async def get_cur_time_str():
    if server_data.redis_dict['time_str']:
        log.success("  [Backend API] Retrieved time ID successfully")
        return {
            "msg": "success", "time_str": server_data.redis_dict['ime_str'],
        }
    else:
        log.error("  [Backend API] No time ID")
        raise HTTPException(status_code=404, detail="time ID not found")


@app.get("/setTimeStr")
async def set_time_str(time_string):
    log.info(f"  [Backend API] Setting time ID to {time_string} ...")
    server_data.set_time_str(time_string)
    log.success(f"  [Backend API] Set time ID to {time_string} successfully")


@app.get("/cleanTimeStr")
async def clean_time_str():
    server_data.clear_time_data()
    log.success("  [Backend API] Cleared time ID successfully")
    return {"msg": "successfully clean!"}



@app.get("/latestPhoto")
async def get_latest_photo():
    if not server_data.redis_dict['latest_photo']:
        raise HTTPException(status_code=404, detail="File not found")
    log.success(f"  [Backend API] Returning photo {server_data.redis_dict['latest_photo']}")
    return FileResponse(server_data.redis_dict['latest_photo'])


@app.get("/latestPhotoData")
async def get_latest_photo_data():
    if not server_data.redis_dict['latest_photo']:
        raise HTTPException(status_code=404, detail="File not found")
    log.success(f"  [Backend API] Returning photo {server_data.redis_dict['latest_photo']}")
    return {
        "time": server_data.redis_dict['photo_time'],
        "photo_path": server_data.redis_dict['latest_photo']
    }


@app.get("/download")
async def download(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    log.success(f"  [Backend API] Returning photo {path}")
    return FileResponse(path)


@app.get("/updatePhotoPath")
async def update_path(time, path):
    server_data.set_photo(path, time)
    log.success("  [Backend API] Updated latest photo info")


@app.get("/updatePos")
async def update_pos(latitude, longitude, time, agent):
    server_data.set_position(float(latitude), float(longitude), time)
    log.success(f"  [Backend API] Updated position for {agent}")


@app.get("/updateHeight")
async def update_h(height, time, agent):
    server_data.set_height(float(height), time)
    log.success(f"  [Backend API] Updated height for {agent}")


@app.get("/height")
async def get_height():
    if server_data.redis_dict['height'] is None:
        raise HTTPException(status_code=404, detail="Not upload position yet")
    else:
        log.success("  [Backend API] Returning height")
        return {
            "height": server_data.redis_dict['height'],
            "time": server_data.redis_dict['height_time']
        }


@app.get("/setOrientation")
async def update_orientation(orientation, time, agent):
    server_data.set_yaw(float(orientation), time)
    log.success(f"  [Backend API] Updated orientation for {agent}")


@app.get("/orientation")
async def get_yaw():
    if server_data.redis_dict['yaw'] is None:
        raise HTTPException(status_code=404, detail="Not upload orientation yet")
    else:
        log.success("  [Backend API] Returning orientation")
        return {
            "orientation": server_data.redis_dict['yaw'],
            "time": server_data.redis_dict['yaw_time']
        }


@app.get("/pos")
async def get_pos():
    if server_data.redis_dict['latitude'] < 0:
        raise HTTPException(status_code=404, detail="Not upload position yet")
    else:
        log.success("  [Backend API] Returning position")
        if server_data.redis_dict['xy'][0] is not None:
            return {
                "longitude": server_data.redis_dict['longitude'],
                "latitude": server_data.redis_dict['latitude'],
                "current_pos": server_data.redis_dict['xy'],
                "time": server_data.redis_dict['location_time']
            }
        return {
            "longitude": server_data.redis_dict['longitude'],
            "latitude": server_data.redis_dict['latitude'],
            "time": server_data.redis_dict['location_time']
        }


@app.get("/setOriginPos")
async def set_origin_pos(latitude, longitude, height, time):
    try: 
        height = float(height)
    except Exception as e:
        height = 0
        log.success(f"  [Backend API] Failed to set initial height, error {e}")
    server_data.set_origin(
        origin_latitude=float(latitude), origin_longitude=float(longitude), origin_height=float(height),
        origin_time=time
    )
    return {
        "msg": "success"
    }


@app.get("/originPos")
async def get_origin_pos():
    if not server_data.redis_dict['origin_latitude'] >= 0:
        raise HTTPException(status_code=404, detail="N.A.")
    return {
        "longitude": server_data.redis_dict['origin_longitude'],
        "latitude": server_data.redis_dict['origin_latitude'],
        "time": server_data.redis_dict['origin_time'],
        "msg": "success"
    }


@app.get("/cumulativeDistance")
async def get_cumulative_distance():
    if not server_data.redis_dict['origin_latitude'] >= 0:
        raise HTTPException(status_code=404, detail="N.A.")
    return {
        "cumulative_distance": server_data.redis_dict['cumulative_distance'],
        "msg": "success"
    }


@app.get("/originHeight")
async def get_origin_height():
    if not server_data.redis_dict['origin_height'] >= 0:
        raise HTTPException(status_code=404, detail="N.A.")
    return {
        "height": server_data.redis_dict['origin_height'],
        "msg": "success"
    }


@app.get("/setUavControl")
async def set_uav_control_input(vx, vy, vz, yaw):
    server_data.set_uav_control_input(
        x=float(vx), y=float(vy), z=float(vz), yaw=float(yaw)
    )
    return {
        "msg": "success"
    }


@app.get("/uavControl")
async def get_uav_control_input():
    if server_data.redis_dict['control_time'] is None:
        raise HTTPException(status_code=404, detail="N.A.")
    return {
        "v_x": server_data.redis_dict['control_input'][0],
        "v_y": server_data.redis_dict['control_input'][1],
        "v_z": server_data.redis_dict['control_input'][2],
        "yaw": server_data.redis_dict['control_input'][3],
        "time": server_data.redis_dict['control_time'],
        "msg": "success"
    }


@app.get("/setUavControlCmd")
async def set_uav_control_input_cmd(cmd):
    server_data.set_uav_control_cmd(cmd)
    return {
        "msg": "success"
    }


@app.get("/uavControlCmd")
async def get_uav_control_input_cmd():
    if server_data.redis_dict['control_cmd'] == "":
        raise HTTPException(status_code=404, detail="Not upload yet")
    return {
        "cmd": server_data.redis_dict['control_cmd'],
        "time": server_data.redis_dict['cmd_time'],
        "msg": "success"
    }


@app.get("/getAllData")
async def get_all_data():
    if not server_data.redis_dict['time_str']:
        raise HTTPException(status_code=404, detail="N.A.")
    else:
        log.success("  [Backend API] Returning all current data")
        return {
            "longitude": server_data.redis_dict['longitude'],
            "latitude": server_data.redis_dict['latitude'],
            "location_time": server_data.redis_dict['location_time'],
            "height": server_data.redis_dict['height'],
            "height_time": server_data.redis_dict['height_time'],
            "photo_time": server_data.redis_dict['photo_time'],
            "photo_path": server_data.redis_dict['latest_photo']
        }


@app.get("/startUpload")
async def start_upload():
    if not server_data.redis_dict['started']:
        server_data.start_upload()
        log.success("  [Backend API] Starting upload task")
        return {"msg": "Started successfully 🛫"}
    else:
        raise HTTPException(status_code=403, detail="Already started")


@app.get("/endUpload")
async def end_upload():
    if server_data.started:
        server_data.end_upload()
        log.error("  [Backend API] Ending upload task")
        return {"msg": "Stopped successfully ☕"}
    else:
        raise HTTPException(status_code=403, detail="Not started")


@app.get("/restartUpload")
async def restart_upload():
    if server_data.redis_dict['started']:
        server_data.end_upload()
        log.error("  [Backend API] Ending upload task")
        server_data.start_upload()
        log.success("  [Backend API] Starting upload task")
        return {"msg": "Restarted successfully 🤯"}
    else:
        raise HTTPException(status_code=403, detail="Not started")


@app.get("/posData")
async def get_pos_raw_data():
    if server_data.redis_dict['xy'][0] is not None:
        log.success("  [Backend API] Returning position and yaw")
        if server_data.redis_dict['height'] is None:
            return {
                "posData": [
                    server_data.redis_dict['xy'][0], server_data.redis_dict['xy'][1],
                    server_data.redis_dict['yaw'], server_data.redis_dict['location_time'],
                    0
                ]
            }
        else:
            return {
                "posData": [
                    server_data.redis_dict['xy'][0], server_data.redis_dict['xy'][1],
                    server_data.redis_dict['yaw'], server_data.redis_dict['location_time'],
                    server_data.redis_dict['height']
                ]
            }
    log.error("  [Backend API] Failed to return position and yaw")
    raise HTTPException(status_code=404, detail="Not upload position yet")


@app.post("/setLoraData")
async def set_lora_data(lora_data: LoraItem):
    server_data.redis_dict['lora_data'][lora_data.data_type] = lora_data.data
    log.success("  [Backend API] Set LoRa data successfully")


@app.get("/loraData")
async def get_lora_data(data_type):
    if server_data.redis_dict['lora_data'].get(data_type) is None:
        log.error(f"  [Backend API] Failed to return LoRa data {data_type}")
        raise HTTPException(status_code=404, detail=f"Not upload {data_type} yet")
    log.success(f"  [Backend API] Returned LoRa data {data_type} successfully")
    return {"data": server_data.redis_dict['lora_data'][data_type]}


if __name__ == "__main__":
    import uvicorn
    from Tools.ConfigUtils import read_config
    from Tools.FileUtils import check_if_exist, build_run_python_sh
    from Tools.DBUtils import RedisDict
    import shutil
    import subprocess
    config = read_config("Configs/LocalServerConfigs.yaml")
    photo_path = config['PhotoPath']
    pre_clean = config['PreCleanPhoto']
    if pre_clean and os.path.exists(photo_path):
        shutil.rmtree(photo_path)
    check_if_exist(photo_path)
    log.success(f" [Local Data Server] Initialized {photo_path}")

    redis_dict = RedisDict(
        host=config["RedisInfo"]["RedisIP"], port=config["RedisInfo"]["RedisPort"],
        db=config["RedisInfo"]["dbID"]
    )
    init_dict = {
        'lora_data': {}, 'time_str': None, 'longitude': -1, 'latitude': -1,
        'longitude_pre': -1, 'latitude_pre': -1, 'origin_longitude': -1,
        'origin_latitude': -1, 'origin_height': -1, 'origin_time': None,
        'cumulative_distance': -1, 'yaw': None, 'yaw_time': None,
        'xy': [None, None], 'location_time': None, 'height': None,
        'height_time': None, 'latest_photo': None, 'photo_time': None,
        'control_time': None, 'cmd_time': None, 'control_input': [0] * 4,
        'control_cmd': "", 'started': False, 'comStarted': False
    }
    redis_dict.init_keys(init_dict)
    log.success(" [Local Data Server] Redis initialized")

    start_sh_path = config['ShPath']
    start_with_scripts = config["StartWithScripts"]
    start_with_configs = config["StartWithScriptsConfigs"]
    local_url = config["LocalUrl"]
    p_num = len(start_with_scripts)
    start_sh_path = [f"{start_sh_path}/local_server_start_with_{i}.sh" for i in range(p_num)]
    start_with_process = []
    for i in range(p_num):
        build_run_python_sh(
            start_sh_path[i],
            [start_with_scripts[i], start_with_configs[i], local_url]
        )
        start_with_process.append(
            subprocess.Popen(['/bin/bash', start_sh_path[i]], stdin=subprocess.PIPE)
        )
        log.success(f" [Local Data Server] Process file {start_with_scripts[i]} created and started")

    uvicorn.run(app='local_backend_api:app', host='0.0.0.0', port=26969, workers=config['Workers'])

    for p in start_with_process:
        try:
            p.stdin.write("quit \n".encode('utf-8'))
            p.stdin.flush()
            log.success(" [Local Data Server] Process exited successfully")
        except Exception as e:
            log.error(f" [Local Data Server] Failed to exit process: {e}")
    log.success(" [Local Data Server] Shutdown complete")

