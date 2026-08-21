"""Remote aggregation API for the paper's dual-mode communication stack.

This service collects UAV/UGV uploads from the edge side, serves synchronized
telemetry to the operator interface, and keeps remote mission supervision
aligned with the onboard controller state.
"""

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import os
import time
from Models.RemoteServerData import RemoteServerData
from Models.ServerMesegeJsonModel import MissionStateItem
import Tools.LogUtils as log
from Tools.TelemetryUtils import (
    build_ugv_state,
    compass_heading_to_enu_yaw,
    normalize_mission_id,
    validate_follow_parameters,
)
from typing import Optional

server_data: Optional[RemoteServerData] = None


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

MISSION_PHASES = {
    "IDLE",
    "TAKEOFF_REQUESTED",
    "PREPARING",
    "TAKEOFF",
    "POSITIONING",
    "ESCORT",
    "LAND_REQUESTED",
    "RETURNING",
    "DESCENDING",
    "LANDING",
    "FAULT",
}


def get_remote_server_config_path():
    return os.environ.get(
        "AGCS_REMOTE_SERVER_CONFIG",
        "Configs/RemoteServerConfig.yaml",
    )


def get_remote_bind(config):
    """Resolve and validate the configured remote API bind address."""
    host = os.environ.get(
        "AGCS_REMOTE_HOST",
        str(config.get("Host", "0.0.0.0")),
    ).strip()
    if not host:
        raise ValueError("Remote API host must not be empty")
    try:
        port = int(
            os.environ.get(
                "AGCS_REMOTE_PORT",
                config.get("Port", 26969),
            )
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Remote API port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("Remote API port must be in [1, 65535]")
    return host, port


def require_upload_mission(mission_id):
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
    server_data = RemoteServerData(get_remote_server_config_path())
    log.success("[Backend API] Started successfully...")


@app.on_event("shutdown")
async def at_shut_down():
    log.error("[Backend API] Shutting down")


@app.get("/alive")
async def check_alive():
    log.success("  [Backend API] Health check called")
    return {"msg": "I am alive!!"}


@app.get("/curTimeStr")
async def get_cur_time_str():
    if server_data.redis_dict["time_str"]:
        log.success("  [Backend API] Retrieved time ID successfully")
        return {
            "msg": "success", "time_str": server_data.redis_dict["time_str"],
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


@app.post("/uavUploadPhoto")
async def upload_and_save(time: str, file: UploadFile = File(...)):
    log.info("  [Backend API] Receiving photo...")
    file_path = f'{server_data.redis_dict["photo_folder"]}/{file.filename}'
    with open(file_path, 'wb') as f:
        f.write(await file.read())
    server_data.set_uav_upload_photo(file_path, time)
    log.success("  [Backend API] Received photo successfully")
    return {"msg": 'successfully upload!'}

@app.post("/ugvUploadPhoto")
async def ugv_upload_and_save(time: str, file: UploadFile = File(...)):
    log.info("  [Backend API] Receiving UGV photo...")
    file_path = f'{server_data.redis_dict["ugv_photo_folder"]}/{file.filename}'
    with open(file_path, 'wb') as f:
        f.write(await file.read())
    server_data.set_ugv_upload_photo(file_path, time)
    log.success("  [Backend API] Received photo successfully")
    return {"msg": 'successfully upload!'}


@app.get("/uavLatestPhoto")
async def get_latest_photo():
    if not server_data.redis_dict["uav_latest_photo"]:
        raise HTTPException(status_code=404, detail="File not found")
    log.success(f"  [Backend API] Returning photo {server_data.redis_dict['uav_latest_photo']}")
    return FileResponse(server_data.redis_dict['uav_latest_photo'])


@app.get("/ugvLatestPhoto")
async def get_ugv_latest_photo():
    if not server_data.redis_dict['ugv_latest_photo']:
        raise HTTPException(status_code=404, detail="File not found")
    log.success(f"  [Backend API] Returning photo {server_data.redis_dict['ugv_latest_photo']}")
    return FileResponse(server_data.redis_dict['ugv_latest_photo'])


@app.get("/uavLatestPhotoData")
async def get_latest_photo_data():
    if not server_data.redis_dict['uav_latest_photo']:
        raise HTTPException(status_code=404, detail="File not found")
    log.success(f"  [Backend API] Returning photo {server_data.redis_dict['uav_latest_photo']}")
    return {
        "time": server_data.redis_dict['uav_photo_time'],
        "photo_path": server_data.redis_dict['uav_latest_photo']
    }


@app.get("/download")
async def download(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    log.success(f"  [Backend API] Returning photo {path}")
    return FileResponse(path)


# uav_data
@app.get("/updatePos")
async def update_pos(latitude, longitude, time, agent, mission_id=None):
    mission_id = require_upload_mission(mission_id)
    if agent == "UAV":
        stored = server_data.set_uav_position(
            latitude=float(latitude),
            longitude=float(longitude),
            time=time,
            mission_id=mission_id,
        )
    else:
        stored = server_data.set_ugv_position(
            latitude=float(latitude),
            longitude=float(longitude),
            time=time,
            mission_id=mission_id,
        )
    if stored is False:
        raise HTTPException(status_code=409, detail="Mission ID is no longer active")
    log.success(f"  [Backend API] Updated {agent} position")


@app.get("/updateHeight")
async def uav_update_height(height, time, agent, mission_id=None):
    mission_id = require_upload_mission(mission_id)
    if agent == "UAV":
        stored = server_data.set_uav_height(
            float(height), time, mission_id=mission_id
        )
    else:
        stored = server_data.set_ugv_height(
            float(height), time, mission_id=mission_id
        )
    if stored is False:
        raise HTTPException(status_code=409, detail="Mission ID is no longer active")
    log.success(f"  [Backend API] Updated {agent} height")


@app.get("/uavHeight")
async def get_uav_height():
    if server_data.redis_dict['uav_height'] is None:
        raise HTTPException(status_code=404, detail="Not upload position yet")
    else:
        log.success("  [Backend API] Returning UAV height")
        return {
            "height": server_data.redis_dict['uav_height'],
            "time": server_data.redis_dict['uav_height_time']
        }


@app.get("/setOrientation")
async def uav_update_orientation(
    orientation, time, agent, mission_id=None
):
    mission_id = require_upload_mission(mission_id)
    if agent == "UAV":
        stored = server_data.set_uav_orientation(
            float(orientation), time, mission_id=mission_id
        )
    else:
        stored = server_data.set_ugv_orientation(
            float(orientation), time, mission_id=mission_id
        )
    if stored is False:
        raise HTTPException(status_code=409, detail="Mission ID is no longer active")
    log.success(f"  [Backend API] Updated {agent} orientation")


@app.get("/uavOrientation")
async def get_uav_orientation():
    if server_data.redis_dict['uav_orientation'] is None:
        raise HTTPException(status_code=404, detail="Not upload orientation yet")
    else:
        log.success("  [Backend API] Returning UAV orientation")
        return {
            "uav_orientation": compass_heading_to_enu_yaw(
                server_data.redis_dict["uav_orientation"]
            ),
            "time": server_data.redis_dict['uav_orientation_time']
        }


@app.get("/ugvOrientation")
async def get_ugv_orientation():
    if server_data.redis_dict['ugv_orientation'] is None:
        raise HTTPException(status_code=404, detail="Not upload orientation yet")
    else:
        log.success("  [Backend API] Returning UGV orientation")
        return {
            "ugv_orientation": compass_heading_to_enu_yaw(
                server_data.redis_dict["ugv_orientation"]
            ),
            "time": server_data.redis_dict['ugv_orientation_time']
        }


@app.get("/ugvState")
async def get_ugv_state():
    keys = (
        "time_str",
        "ugv_current_pos",
        "ugv_location_time",
        "ugv_orientation",
        "ugv_orientation_time",
        "ugv_height",
        "ugv_height_time",
        "ugv_velocity",
        "ugv_velocity_time",
    )
    snapshot = server_data.redis_dict.get_many(keys)
    try:
        state = build_ugv_state(
            mission_id=snapshot["time_str"],
            current_pos=snapshot["ugv_current_pos"],
            position_time=snapshot["ugv_location_time"],
            filtered_heading=snapshot["ugv_orientation"],
            heading_time=snapshot["ugv_orientation_time"],
            height=snapshot["ugv_height"],
            height_time=snapshot["ugv_height_time"],
            velocity=snapshot["ugv_velocity"],
            velocity_time=snapshot["ugv_velocity_time"],
        )
    except (TypeError, ValueError):
        log.error("  [Backend API] Complete UGV state is not available")
        raise HTTPException(
            status_code=404,
            detail="Complete UGV state for the active mission is not available",
        )
    log.success("  [Backend API] Returning atomic UGV state")
    return state


@app.get("/uavPos")
async def get_uav_pos():
    if server_data.redis_dict['uav_latitude'] < 0:
        raise HTTPException(status_code=404, detail="Not upload position yet")
    else:
        log.success("  [Backend API] Returning UAV position")
        if server_data.redis_dict['uav_current_pos'][0] is not None:
            return {
                "longitude": server_data.redis_dict['uav_longitude'],
                "latitude": server_data.redis_dict['uav_latitude'],
                "current_pos": server_data.redis_dict['uav_current_pos'],
                "time": server_data.redis_dict['uav_location_time']
            }
        return {
            "longitude": server_data.redis_dict['uav_longitude'],
            "latitude": server_data.redis_dict['uav_latitude'],
            "time": server_data.redis_dict['uav_location_time']
        }


# ugv_data
@app.get("/ugvHeight")
async def get_ugv_height():
    if server_data.redis_dict['ugv_height'] is None:
        raise HTTPException(status_code=404, detail="Not upload position yet")
    else:
        log.success("  [Backend API] Returning UGV height")
        return {
            "height": server_data.redis_dict['ugv_height'],
            "time": server_data.redis_dict['ugv_height_time']
        }


@app.get("/ugvPos")
async def get_ugv_pos():
    if server_data.redis_dict['ugv_latitude'] < 0:
        raise HTTPException(status_code=404, detail="Not upload position yet")
    else:
        log.success("  [Backend API] Returning UGV position")
        if server_data.redis_dict['ugv_current_pos'][0] is not None:
            return {
                "longitude": server_data.redis_dict['ugv_longitude'],
                "latitude": server_data.redis_dict['ugv_latitude'],
                "current_pos": server_data.redis_dict['ugv_current_pos'],
                "time": server_data.redis_dict['ugv_location_time']
            }
        return {
            "longitude": server_data.redis_dict['ugv_longitude'],
            "latitude": server_data.redis_dict['ugv_latitude'],
            "time": server_data.redis_dict['ugv_location_time']
        }


@app.get("/setThreshold")
async def set_threshold(threshold):
    server_data.set_threshold(threshold=float(threshold))
    return {
        "threshold": server_data.redis_dict['threshold'],
        "msg": "success"
    }


@app.get("/setOriginPos")
async def set_origin_pos():
    if not server_data.set_origin_pos():
        log.error("  [Backend API] Failed to set origin point")
        raise HTTPException(status_code=403, detail=f"Not set yet, threshold {server_data.redis_dict['threshold']:.2f}, {server_data.redis_dict['uav_ugv_distance']:.2f}")
    else:
        log.success("  [Backend API] Origin point set successfully")
        return {
            "longitude": server_data.redis_dict['origin_longitude'],
            "latitude": server_data.redis_dict['origin_latitude'],
            "uav_height": server_data.redis_dict['origin_uav_height'],
            "ugv_height": server_data.redis_dict['origin_ugv_height'],
            "time": server_data.redis_dict['origin_time'],
            "msg": "success"
        }


@app.get("/originPos")
async def get_origin_pos():
    if not server_data.redis_dict['origin_latitude'] >= 0:
        log.error("  [Backend API] Failed to get origin point")
        raise HTTPException(status_code=404, detail=f"Not set yet, threshold {server_data.redis_dict['threshold']:.2f}, current {server_data.redis_dict['uav_ugv_distance']:.2f}")
    else:
        log.success("  [Backend API] Origin point retrieved successfully")
        return {
            "longitude": server_data.redis_dict['origin_longitude'],
            "latitude": server_data.redis_dict['origin_latitude'],
            "uav_height": server_data.redis_dict['origin_uav_height'],
            "ugv_height": server_data.redis_dict['origin_ugv_height'],
            "time": server_data.redis_dict['origin_time'],
            "msg": "success"
        }


@app.get("/setOriginHeight")
async def set_origin_height():
    if not server_data.set_origin_pos():
        log.error("  [Backend API] Failed to set origin height")
        raise HTTPException(status_code=403, detail=f"Not set yet, threshold {server_data.redis_dict['threshold']:.2f}, {server_data.redis_dict['uav_ugv_distance']:.2f}")
    else:
        log.success("  [Backend API] Origin height set successfully")
        return {
            "origin_uav_height": server_data.redis_dict['origin_uav_height'],
            "origin_ugv_height": server_data.redis_dict['origin_ugv_height'],
            "msg": "success"
        }


@app.get("/originHeight")
async def get_origin_height():
    if not server_data.redis_dict['origin_ugv_height'] >= 0:
        log.error("  [Backend API] Failed to get origin height")
        raise HTTPException(status_code=404, detail="Not set yet")
    else:
        log.success("  [Backend API] Origin height retrieved successfully")
        return {
            "origin_uav_height": server_data.redis_dict['origin_uav_height'],
            "origin_ugv_height": server_data.redis_dict['origin_ugv_height'],
            "msg": "success"
        }


@app.get("/setEmergencyStop")
async def set_emergency_stop():
    server_data.set_emergency_stop()
    log.success("  [Backend API] Emergency stop triggered")
    return {
        "emergency_stop_flag": server_data.redis_dict['emergency_stop'],
        "msg": "success"
    }


@app.get("/clearEmergencyStop")
async def clear_emergency_stop():
    server_data.clear_emergency_stop()
    log.success("  [Backend API] Emergency stop cleared")
    return {
        "emergency_stop_flag": server_data.redis_dict['emergency_stop'],
        "msg": "success",
    }


@app.get("/emergencyData")
async def get_emergency_data():
    snapshot = server_data.redis_dict.get_many(
        ("time_str", "emergency_stop")
    )
    mission_id = normalize_mission_id(snapshot["time_str"])
    if mission_id is None:
        raise HTTPException(status_code=404, detail="No active mission")
    return {
        "emergencyData": [
            bool(snapshot["emergency_stop"]),
            mission_id,
            time.time(),
        ]
    }


@app.get("/getDistance")
async def get_distance_api():
    log.success("  [Backend API] Distance requested")
    return {
        "msg": "success",
        "distance": server_data.get_distance()
    }

@app.get("/emergencyStop")
async def get_emergency_stop():
    if not server_data.redis_dict['emergency_stop']:
        log.error("  [Backend API] Emergency stop not active")
        raise HTTPException(status_code=403, detail="Not emergency stop")
    else:
        log.success("  [Backend API] Emergency stop triggered")
        return {
            "emergency_stop_flag": server_data.redis_dict['emergency_stop'],
            "msg": "success"
        }


@app.get("/setDepart")
async def set_depart():
    mission_id = normalize_mission_id(server_data.redis_dict["time_str"])
    if mission_id is None:
        raise HTTPException(
            status_code=409,
            detail="Initialize a mission before requesting takeoff",
        )
    server_data.set_depart()
    server_data.set_mission_state(
        mission_id,
        "TAKEOFF_REQUESTED",
    )
    log.success("  [Backend API] Takeoff command issued")
    return {
        "msg": "takeoff request accepted",
        "mission_id": mission_id,
        "phase": "TAKEOFF_REQUESTED",
    }


@app.get("/setLand")
async def set_land():
    mission_id = normalize_mission_id(server_data.redis_dict["time_str"])
    if mission_id is None:
        raise HTTPException(
            status_code=409,
            detail="No active mission is available for landing",
        )
    server_data.set_land()
    server_data.set_mission_state(
        mission_id,
        "LAND_REQUESTED",
    )
    log.success("  [Backend API] Landing command issued")
    return {
        "msg": "landing request accepted",
        "mission_id": mission_id,
        "phase": "LAND_REQUESTED",
    }


@app.post("/missionState")
async def set_mission_state(item: MissionStateItem):
    mission_id = require_upload_mission(item.mission_id)
    phase = str(item.phase).strip().upper()
    if phase not in MISSION_PHASES:
        raise HTTPException(status_code=422, detail="Unknown mission phase")
    active_source = item.active_source
    if active_source is not None:
        active_source = str(active_source).strip().lower()
        if active_source not in {"cellular", "lora"}:
            raise HTTPException(
                status_code=422,
                detail="active_source must be cellular or lora",
            )
    if not server_data.set_mission_state(
        mission_id,
        phase,
        active_source,
        item.airborne,
        True,
    ):
        raise HTTPException(
            status_code=409,
            detail="Mission state belongs to an inactive mission",
        )
    return {
        "msg": "mission state stored",
        "mission_id": mission_id,
        "phase": phase,
        "active_source": active_source,
        "airborne": item.airborne,
    }


@app.get("/missionState")
async def get_mission_state():
    keys = (
        "time_str",
        "mission_phase",
        "mission_phase_time",
        "mission_controller_time",
        "mission_active_source",
        "mission_airborne",
    )
    snapshot = server_data.redis_dict.get_many(keys)
    mission_id = normalize_mission_id(snapshot["time_str"])
    if mission_id is None or snapshot["mission_phase"] is None:
        raise HTTPException(status_code=404, detail="Mission state unavailable")
    updated_at = snapshot["mission_phase_time"]
    controller_updated_at = snapshot["mission_controller_time"]
    age = (
        None
        if controller_updated_at is None
        else max(0.0, time.time() - controller_updated_at)
    )
    return {
        "mission_id": mission_id,
        "phase": snapshot["mission_phase"],
        "active_source": snapshot["mission_active_source"],
        "updated_at": updated_at,
        "controller_updated_at": controller_updated_at,
        "age": age,
        "controller_online": age is not None and age <= 3.0,
        "airborne": bool(snapshot["mission_airborne"]),
    }


@app.get("/depart")
async def get_depart():
    if not server_data.redis_dict['depart']:
        log.error("  [Backend API] No takeoff action")
        raise HTTPException(status_code=403, detail="Not depart")
    else:
        log.success("  [Backend API] Takeoff active")
        return {
            "depart_flag": server_data.redis_dict['depart'],
            "msg": "success"
        }


@app.get("/uavUgvPos")
async def get_uav_ugv_pos():
    if server_data.redis_dict['ugv_latitude'] < 0 or server_data.redis_dict['uav_latitude'] < 0:
        raise HTTPException(status_code=404, detail="Not upload position yet")
    else:
        log.success("  [Backend API] Returning UAV and UGV positions")
        return {
            "uav_latitude": server_data.redis_dict['uav_latitude'],
            "uav_longitude": server_data.redis_dict['uav_longitude'],
            "ugv_latitude": server_data.redis_dict['ugv_latitude'],
            "ugv_longitude": server_data.redis_dict['ugv_longitude'],
            "uav_ugv_distance": server_data.redis_dict['uav_ugv_distance'],
            "time": server_data.redis_dict['ugv_location_time']
        }

@app.get("/setDH")
async def set_DH(D, H):
    try:
        guiding_distance, flight_height = validate_follow_parameters(
            float(D), float(H)
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    server_data.set_DH(guiding_distance, flight_height)
    log.success("  [Backend API] Set D and H")
    return {
        "D": guiding_distance,
        "H": flight_height,
        "msg": "success",
    }


@app.get("/checkDH")
async def get_depart():
    if server_data.redis_dict['D'] is None:
        log.error("  [Backend API] D/H not set")
        raise HTTPException(status_code=403, detail="Not set")
    else:
        log.success("  [Backend API] Returning D/H")
        return {
            "D": server_data.redis_dict['D'],
            "H": server_data.redis_dict['H'],
            "t": server_data.redis_dict['DH_t'],
            "msg": "success"
        }


@app.get("/systemData")
async def get_system_data():
    log.success("  [Backend API] Returning system data")
    return {
        "D": server_data.redis_dict['D'],
        "depart": server_data.redis_dict['depart'],
        "H": server_data.redis_dict['H'],
        "msg": "success",
        "ugv_h": server_data.redis_dict['ugv_height'],
        "ugv_t": server_data.redis_dict['ugv_location_time'],
        "uav_h": server_data.redis_dict['uav_height'],
        "uav_t": server_data.redis_dict['uav_location_time'],
        "uav_yaw": (
            None
            if server_data.redis_dict["uav_orientation"] is None
            else compass_heading_to_enu_yaw(
                server_data.redis_dict["uav_orientation"]
            )
        ),
        "ugv_yaw": (
            None
            if server_data.redis_dict["ugv_orientation"] is None
            else compass_heading_to_enu_yaw(
                server_data.redis_dict["ugv_orientation"]
            )
        ),
        "distance": server_data.get_distance(),
        "mission_phase": server_data.redis_dict["mission_phase"],
        "mission_active_source": server_data.redis_dict[
            "mission_active_source"
        ],
        "mission_airborne": bool(
            server_data.redis_dict["mission_airborne"]
        ),
    }


@app.get("/systemPos")
async def get_system_pos():
    log.success("  [Backend API] Returning system pos")
    return {
        "uav_longitude": server_data.redis_dict['uav_longitude'],
        "uav_latitude": server_data.redis_dict['uav_latitude'],
        "ugv_longitude": server_data.redis_dict['ugv_longitude'],
        "ugv_latitude": server_data.redis_dict['ugv_latitude'],
    }


if __name__ == "__main__":
    import uvicorn
    from Tools.ConfigUtils import read_config
    from Tools.FileUtils import check_if_exist
    from Tools.DBUtils import RedisDict
    import shutil
    config = read_config(get_remote_server_config_path())

    photo_path = os.path.abspath(config['PhotoPath'])
    pre_clean = config['PreCleanPath']

    if pre_clean and os.path.exists(photo_path):
        shutil.rmtree(photo_path)
    check_if_exist(photo_path)
    log.success(f" [Remote Data Server] Initialized data directory {photo_path}")

    redis_dict = RedisDict(
        host=config["RedisInfo"]["RedisIP"], port=config["RedisInfo"]["RedisPort"],
        db=config["RedisInfo"]["dbID"]
    )
    init_dict = {
        "time_str": None, "photo_folder": None, "ugv_photo_folder": None,
        "uav_photo_table_name": None, "uav_longitude": -1, "uav_latitude": -1,
        "uav_location_time": None, "uav_height": None, "uav_height_time": None,
        "uav_latest_photo": None, "ugv_latest_photo": None,
        "uav_photo_time": None, "ugv_photo_time": None,
        "ugv_longitude": -1, "ugv_latitude": -1,
        "ugv_location_time": None, "uav_ugv_distance": -1,
        "ugv_velocity": [0.0, 0.0], "ugv_velocity_time": None,
        "ugv_height": None, "ugv_height_time": None,
        "ugv_orientation": None, "ugv_orientation_time": None,
        "uav_orientation": None, "uav_orientation_time": None,
        "origin_uav_height": -1, "origin_ugv_height": -1,
        "origin_latitude": -1, "origin_longitude": -1,
        "origin_time": None, "threshold": 2, "emergency_stop": False,
        "depart": False, "uav_current_pos": [None, None],
        "ugv_current_pos": [None, None], "D": None, "H": None, "DH_t": 0,
        "mission_phase": None, "mission_phase_time": None,
        "mission_controller_time": None,
        "mission_active_source": None,
        "mission_airborne": False,
    }
    redis_dict.init_keys(init_dict)
    log.success(" [Remote Data Server] Redis initialized")

    bind_host, bind_port = get_remote_bind(config)
    uvicorn.run(
        app='remote_backend_api:app',
        host=bind_host,
        port=bind_port,
        workers=config['Workers'],
    )
