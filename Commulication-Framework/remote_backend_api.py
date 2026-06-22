"""Remote aggregation API for the paper's dual-mode communication stack.

This service collects UAV/UGV uploads from the edge side, serves synchronized
telemetry to the operator interface, and keeps remote mission supervision
aligned with the onboard controller state.
"""

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
import os
from Models.RemoteServerData import RemoteServerData
import Tools.LogUtils as log
from typing import Optional

server_data: Optional[RemoteServerData] = None


app = FastAPI()


@app.on_event("startup")
async def at_start_up():
    global server_data
    server_data = RemoteServerData("Configs/RemoteServerConfig.yaml")
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
    server_data.set_time_str(time_string)
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
async def update_pos(latitude, longitude, time, agent):
    if agent == "UAV":
        server_data.set_uav_position(latitude=float(latitude), longitude=float(longitude), time=time)
        log.success("  [Backend API] Updated UAV position")
    else:
        server_data.set_ugv_position(latitude=float(latitude), longitude=float(longitude), time=time)
        log.success("  [Backend API] Updated UGV position")


@app.get("/updateHeight")
async def uav_update_height(height, time, agent):
    if agent == "UAV":
        server_data.set_uav_height(float(height), time)
        log.success("  [Backend API] Updated UAV height")
    else:
        server_data.set_ugv_height(float(height), time)
        log.success("  [Backend API] Updated UGV height")


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
async def uav_update_orientation(orientation, time, agent):
    if agent == "UAV":
        server_data.set_uav_orientation(float(orientation), time)
        log.success("  [Backend API] Updated UAV orientation")
    else:
        server_data.set_ugv_orientation(float(orientation), time)
        log.success("  [Backend API] Updated UGV orientation")


@app.get("/uavOrientation")
async def get_uav_orientation():
    if server_data.redis_dict['uav_orientation'] is None:
        raise HTTPException(status_code=404, detail="Not upload orientation yet")
    else:
        log.success("  [Backend API] Returning UAV orientation")
        return {
            "uav_orientation": server_data.redis_dict['uav_orientation'],
            "time": server_data.redis_dict['uav_orientation_time']
        }


@app.get("/ugvOrientation")
async def get_ugv_orientation():
    if server_data.redis_dict['ugv_orientation'] is None:
        raise HTTPException(status_code=404, detail="Not upload orientation yet")
    else:
        log.success("  [Backend API] Returning UGV orientation")
        return {
            "ugv_orientation": server_data.redis_dict['ugv_orientation'],
            "time": server_data.redis_dict['ugv_orientation_time']
        }


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
    server_data.set_depart()
    log.success("  [Backend API] Takeoff command issued")
    return {
        "msg": f"success, change, depart -> {server_data.redis_dict['depart']}"
    }


@app.get("/setLand")
async def set_land():
    server_data.set_land()
    log.success("  [Backend API] Landing command issued")
    return {
        "msg": f"success, change, depart -> {server_data.redis_dict['depart']}"
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
    server_data.set_DH(float(D), float(H))
    log.success("  [Backend API] Set D and H")
    return {
        "msg": f"success -> {D} {H}"
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
        "uav_yaw": server_data.redis_dict['uav_orientation'],
        "ugv_yaw": server_data.redis_dict['ugv_orientation'],
        "distance": server_data.get_distance(),
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
    config = read_config("Configs/RemoteServerConfig.yaml")

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
        "ugv_height": None, "ugv_height_time": None,
        "ugv_orientation": None, "ugv_orientation_time": None,
        "uav_orientation": None, "uav_orientation_time": None,
        "origin_uav_height": -1, "origin_ugv_height": -1,
        "origin_latitude": -1, "origin_longitude": -1,
        "origin_time": None, "threshold": 2, "emergency_stop": False,
        "depart": False, "uav_current_pos": [None, None],
        "ugv_current_pos": [None, None], "D": None, "H": None, "DH_t": 0
    }
    redis_dict.init_keys(init_dict)
    log.success(" [Remote Data Server] Redis initialized")

    uvicorn.run(app='remote_backend_api:app', host='0.0.0.0', port=26969, workers=config['Workers'])
