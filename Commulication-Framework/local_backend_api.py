"""Edge-side FastAPI service for the local node in the cooperative system.

The local backend is the control-facing API used by onboard components. It
stores the freshest UAV-side state and exposes the command/data endpoints that
the controller consumes during follow and return tasks.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import math
import os
import time
from Models.LocalServerData import LocalServerData
import Tools.LogUtils as log
from Tools.TelemetryUtils import (
    build_position_heading_packet,
    normalize_mission_id,
)
from typing import Optional

from Models.ServerMesegeJsonModel import LoraItem

server_data: Optional[LocalServerData] = None

app = FastAPI()
LORA_EMERGENCY_FRESHNESS_SECONDS = 1.0


def get_local_server_config_path():
    return os.environ.get(
        "AGCS_LOCAL_SERVER_CONFIG",
        "Configs/LocalServerConfigs.yaml",
    )


def require_upload_mission(mission_id, agent, allow_uav_legacy=False):
    if mission_id is None and allow_uav_legacy and agent == "UAV":
        return None
    mission_id = normalize_mission_id(mission_id)
    if mission_id is None:
        raise HTTPException(
            status_code=422,
            detail="mission_id is required for telemetry uploads",
        )
    return mission_id


@app.on_event("startup")
async def at_start_up():
    global server_data
    server_data = LocalServerData(get_local_server_config_path())
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
            "msg": "success", "time_str": server_data.redis_dict['time_str'],
        }
    else:
        log.error("  [Backend API] No time ID")
        raise HTTPException(status_code=404, detail="time ID not found")


@app.get("/setTimeStr")
async def set_time_str(time_string):
    log.info(f"  [Backend API] Setting time ID to {time_string} ...")
    if server_data.set_time_str(time_string) is False:
        raise HTTPException(
            status_code=409,
            detail="Mission ID is older than the active mission",
        )
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
async def update_pos(latitude, longitude, time, agent, mission_id=None):
    mission_id = require_upload_mission(mission_id, agent)
    stored = server_data.set_position(
        float(latitude),
        float(longitude),
        time,
        mission_id=mission_id,
    )
    if stored is False:
        raise HTTPException(status_code=409, detail="Mission ID is no longer active")
    log.success(f"  [Backend API] Updated position for {agent}")


@app.get("/updateHeight")
async def update_h(height, time, agent, mission_id=None):
    mission_id = require_upload_mission(mission_id, agent)
    stored = server_data.set_height(
        float(height), time, mission_id=mission_id
    )
    if stored is False:
        raise HTTPException(status_code=409, detail="Mission ID is no longer active")
    log.success(f"  [Backend API] Updated height for {agent}")


@app.get("/height")
async def get_height():
    snapshot = server_data.redis_dict.get_many(
        ("height", "height_time", "time_str")
    )
    if snapshot['height'] is None:
        raise HTTPException(status_code=404, detail="Not upload position yet")
    else:
        log.success("  [Backend API] Returning height")
        return {
            "height": snapshot['height'],
            "time": snapshot['height_time'],
            "mission_id": normalize_mission_id(snapshot['time_str']),
        }


@app.get("/setOrientation")
async def update_orientation(
    orientation, time, agent, mission_id=None
):
    mission_id = require_upload_mission(
        mission_id,
        agent,
        allow_uav_legacy=True,
    )
    stored = server_data.set_yaw(
        float(orientation), time, mission_id=mission_id
    )
    if stored is False:
        raise HTTPException(status_code=409, detail="Mission ID is no longer active")
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
    keys = ("time_str", "longitude", "latitude", "xy", "location_time")
    snapshot = server_data.redis_dict.get_many(keys)
    mission_id = normalize_mission_id(snapshot["time_str"])
    if snapshot["latitude"] < 0:
        raise HTTPException(status_code=404, detail="Not upload position yet")
    else:
        log.success("  [Backend API] Returning position")
        if snapshot["xy"][0] is not None:
            return {
                "longitude": snapshot["longitude"],
                "latitude": snapshot["latitude"],
                "current_pos": snapshot["xy"],
                "time": snapshot["location_time"],
                "mission_id": mission_id,
            }
        return {
            "longitude": snapshot["longitude"],
            "latitude": snapshot["latitude"],
            "time": snapshot["location_time"],
            "mission_id": mission_id,
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
    snapshot = server_data.redis_dict.get_many(
        ("control_input", "control_time")
    )
    if snapshot['control_time'] is None:
        raise HTTPException(status_code=404, detail="N.A.")
    return {
        "v_x": snapshot['control_input'][0],
        "v_y": snapshot['control_input'][1],
        "v_z": snapshot['control_input'][2],
        "yaw": snapshot['control_input'][3],
        "time": snapshot['control_time'],
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
    snapshot = server_data.redis_dict.get_many(
        ("control_cmd", "cmd_time")
    )
    if snapshot['control_cmd'] == "":
        raise HTTPException(status_code=404, detail="Not upload yet")
    return {
        "cmd": snapshot['control_cmd'],
        "time": snapshot['cmd_time'],
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
        try:
            server_data.start_upload()
        except (OSError, RuntimeError, ValueError) as exc:
            log.error(f"  [Backend API] Upload task failed to start: {exc}")
            raise HTTPException(
                status_code=503,
                detail=f"Upload task failed to start: {exc}",
            )
        log.success("  [Backend API] Starting upload task")
        return {"msg": "Started successfully 🛫"}
    else:
        raise HTTPException(status_code=403, detail="Already started")


@app.get("/endUpload")
async def end_upload():
    if server_data.redis_dict['started']:
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
        try:
            server_data.start_upload()
        except (OSError, RuntimeError, ValueError) as exc:
            log.error(f"  [Backend API] Upload task failed to restart: {exc}")
            raise HTTPException(
                status_code=503,
                detail=f"Upload task failed to restart: {exc}",
            )
        log.success("  [Backend API] Starting upload task")
        return {"msg": "Restarted successfully 🤯"}
    else:
        raise HTTPException(status_code=403, detail="Not started")


@app.get("/posData")
async def get_pos_raw_data():
    keys = (
        "time_str",
        "xy",
        "yaw",
        "location_time",
        "yaw_time",
        "height",
        "velocity",
    )
    snapshot = server_data.redis_dict.get_many(keys)
    try:
        packet = build_position_heading_packet(
            position=snapshot["xy"],
            yaw=snapshot["yaw"],
            location_time=snapshot["location_time"],
            yaw_time=snapshot["yaw_time"],
            height=snapshot["height"],
            velocity=snapshot["velocity"],
            mission_id=snapshot["time_str"],
        )
        log.success("  [Backend API] Returning position and yaw")
        return {"posData": packet}
    except (TypeError, ValueError):
        log.error("  [Backend API] Failed to return position and yaw")
        raise HTTPException(
            status_code=404,
            detail="A synchronized position/yaw sample is not available yet",
        )


@app.post("/setLoraData")
async def set_lora_data(lora_data: LoraItem):
    if lora_data.data_type not in {"posData", "emergencyData"}:
        raise HTTPException(status_code=422, detail="Unsupported LoRa data type")
    if (
        lora_data.data_type == "emergencyData"
        and (
            len(lora_data.data) < 2
            or not isinstance(lora_data.data[0], bool)
            or normalize_mission_id(lora_data.data[1]) is None
            or len(lora_data.data) < 3
            or isinstance(lora_data.data[2], bool)
            or not isinstance(lora_data.data[2], (int, float))
            or not math.isfinite(float(lora_data.data[2]))
        )
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "emergencyData must be "
                "[boolean, mission_id, source_time]"
            ),
        )
    received_at = (
        time.time()
        if getattr(lora_data, "received_at", None) is None
        else float(lora_data.received_at)
    )
    if not math.isfinite(received_at):
        raise HTTPException(
            status_code=422,
            detail="LoRa receive time must be finite",
        )
    setter = getattr(server_data, "set_lora_data", None)
    if setter is not None:
        setter(lora_data.data_type, lora_data.data, received_at)
    else:
        updated_data = dict(server_data.redis_dict['lora_data'] or {})
        received_times = dict(
            server_data.redis_dict['lora_received_at'] or {}
        )
        updated_data[lora_data.data_type] = lora_data.data
        received_times[lora_data.data_type] = received_at
        set_many = getattr(server_data.redis_dict, "set_many", None)
        if set_many is not None:
            set_many({
                'lora_data': updated_data,
                'lora_received_at': received_times,
            })
        else:
            server_data.redis_dict['lora_data'] = updated_data
            server_data.redis_dict['lora_received_at'] = received_times
    log.success("  [Backend API] Set LoRa data successfully")
    return {"msg": "success", "received_at": received_at}


@app.get("/loraData")
async def get_lora_data(data_type):
    lora_data = server_data.redis_dict['lora_data'] or {}
    if lora_data.get(data_type) is None:
        log.error(f"  [Backend API] Failed to return LoRa data {data_type}")
        raise HTTPException(status_code=404, detail=f"Not upload {data_type} yet")
    log.success(f"  [Backend API] Returned LoRa data {data_type} successfully")
    return {"data": lora_data[data_type]}


@app.get("/loraLinkStatus")
async def get_lora_link_status(data_type, timeout=0.75):
    try:
        timeout = float(timeout)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="timeout must be numeric")
    if timeout <= 0:
        raise HTTPException(status_code=422, detail="timeout must be positive")
    received_times = server_data.redis_dict['lora_received_at'] or {}
    received_at = received_times.get(data_type)
    if received_at is None:
        raise HTTPException(
            status_code=404,
            detail=f"No LoRa heartbeat received for {data_type}",
        )
    age_seconds = time.time() - float(received_at)
    return {
        "data_type": data_type,
        "received_at": float(received_at),
        "age_seconds": age_seconds,
        "healthy": 0.0 <= age_seconds <= timeout,
    }


@app.get("/setEmergencyStop")
async def set_emergency_stop():
    setter = getattr(server_data, "set_emergency_stop", None)
    if setter is not None:
        setter(True)
    else:
        server_data.redis_dict['emergency_stop'] = True
    return {"emergency_stop_flag": True, "msg": "success"}


@app.get("/clearEmergencyStop")
async def clear_emergency_stop():
    setter = getattr(server_data, "set_emergency_stop", None)
    if setter is not None:
        setter(False)
    else:
        server_data.redis_dict['emergency_stop'] = False
    return {"emergency_stop_flag": False, "msg": "success"}


@app.get("/emergencyData")
async def get_emergency_data():
    snapshot = server_data.redis_dict.get_many(
        ("time_str", "emergency_stop")
    )
    mission_id = normalize_mission_id(snapshot['time_str'])
    if mission_id is None:
        raise HTTPException(status_code=404, detail="No active mission")
    return {
        "emergencyData": [
            bool(snapshot['emergency_stop']),
            mission_id,
            time.time(),
        ]
    }


@app.get("/emergencyStop")
async def get_emergency_stop():
    snapshot = server_data.redis_dict.get_many(
        (
            "time_str",
            "emergency_stop",
            "lora_data",
            "lora_received_at",
        )
    )
    mission_id = normalize_mission_id(snapshot['time_str'])
    direct_stop = bool(snapshot['emergency_stop'])
    lora_data = snapshot['lora_data'] or {}
    received_times = snapshot['lora_received_at'] or {}
    lora_stop = lora_data.get("emergencyData")
    matching_command = (
        isinstance(lora_stop, list)
        and len(lora_stop) >= 3
        and normalize_mission_id(lora_stop[1]) == mission_id
    )
    if direct_stop or (matching_command and lora_stop[0] is True):
        return {"emergency_stop_flag": True, "msg": "success"}
    if not matching_command:
        raise HTTPException(
            status_code=503,
            detail="LoRa emergency state is unavailable",
        )
    received_at = received_times.get("emergencyData")
    now = time.time()
    radio_age = (
        float("inf")
        if received_at is None
        else now - float(received_at)
    )
    source_age = now - float(lora_stop[2])
    is_fresh = (
        0.0 <= radio_age <= LORA_EMERGENCY_FRESHNESS_SECONDS
        and 0.0 <= source_age <= LORA_EMERGENCY_FRESHNESS_SECONDS
    )
    if not is_fresh:
        raise HTTPException(
            status_code=503,
            detail="LoRa emergency state is stale",
        )
    if lora_stop[0] is False:
        raise HTTPException(status_code=403, detail="Not emergency stop")
    raise HTTPException(status_code=503, detail="Invalid LoRa emergency state")


if __name__ == "__main__":
    import sys
    import uvicorn
    from Tools.ConfigUtils import read_config
    from Tools.FileUtils import check_if_exist, build_run_python_sh
    from Tools.DBUtils import RedisDict
    import shutil
    import subprocess
    config_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else get_local_server_config_path()
    )
    config_path = os.path.abspath(config_path)
    os.environ["AGCS_LOCAL_SERVER_CONFIG"] = config_path
    config = read_config(config_path)
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
        'lora_data': {}, 'lora_received_at': {}, 'emergency_stop': False,
        'time_str': None, 'longitude': -1, 'latitude': -1,
        'longitude_pre': -1, 'latitude_pre': -1, 'origin_longitude': -1,
        'origin_latitude': -1, 'origin_height': -1, 'origin_time': None,
        'cumulative_distance': -1, 'yaw': None, 'yaw_time': None,
        'xy': [None, None], 'location_time': None,
        'velocity': [0.0, 0.0], 'velocity_time': None, 'height': None,
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
    upload_config = read_config(
        config.get("MainUploadConfig", "./Configs/UploadMainConfig.yaml")
    )
    remote_url = upload_config.get("RemoteURL")
    p_num = len(start_with_scripts)
    start_sh_path = [f"{start_sh_path}/local_server_start_with_{i}.sh" for i in range(p_num)]
    start_with_process = []
    for i in range(p_num):
        build_run_python_sh(
            start_sh_path[i],
            [
                start_with_scripts[i],
                start_with_configs[i],
                local_url,
                remote_url,
            ]
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
