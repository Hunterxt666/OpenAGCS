import math

import requests
import Tools.LogUtil as log


def get(url, timeout=0.5):
    try:
        re = requests.get(url, timeout=timeout)
        return re
    except Exception as e:
        log.error(f"      [requests]{url}request failed, error: {e}")
        return None


def _get_json(url, timeout=0.5):
    response = get(url, timeout=timeout)
    if response is None or response.status_code != 200:
        return None
    try:
        return response.json()
    except (TypeError, ValueError) as error:
        log.error(f"      [requests]{url} returned invalid JSON: {error}")
        return None


def get_pos(url):
    return _get_json(f"{url}/pos")


def get_pos_remote(url):
    return _get_json(f"{url}/ugvPos")


def get_orientation_remote(url):
    return _get_json(f"{url}/ugvOrientation")


def _mission_id(value):
    if value is None or isinstance(value, bool):
        raise ValueError("mission_id must be a non-empty string")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("mission_id must be a non-empty string")
    return normalized


def get_cellular_gv_state(url):
    """Read one epoch-tagged GV state snapshot over the cellular path."""
    payload = _get_json(f"{url}/ugvState")
    if not payload:
        return None
    try:
        mission_id = _mission_id(payload["mission_id"])
        position_time = float(payload["position_time"])
        orientation_time = float(payload["heading_time"])
        position = payload["current_pos"]
        if not isinstance(position, (list, tuple)) or len(position) != 2:
            raise ValueError("current_pos must contain x and y")
        position = tuple(float(value) for value in position)
        yaw_degrees = float(payload["filtered_heading"])
        height = payload.get("height")
        height = None if height is None else float(height)
        velocity = payload.get("current_velocity")
        if velocity is not None:
            if not isinstance(velocity, (list, tuple)) or len(velocity) != 2:
                raise ValueError("current_velocity must contain east and north")
            velocity = tuple(float(value) for value in velocity)
        values = (
            *position,
            yaw_degrees,
            position_time,
            orientation_time,
            *(() if height is None else (height,)),
            *(() if velocity is None else velocity),
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("cellular GV state values must be finite")
        return {
            "mission_id": mission_id,
            "sample_id": (
                mission_id,
                position_time,
                orientation_time,
            ),
            "position": position,
            "yaw_degrees": yaw_degrees,
            "height": height,
            "velocity": velocity,
            "sensed_at": min(position_time, orientation_time),
        }
    except (KeyError, TypeError, ValueError) as error:
        log.error(f"      [requests]invalid cellular GV state: {error}")
        return None


def get_lora_gv_state(url):
    """Read the latest combined GV state delivered over LoRa."""
    payload = _get_json(f"{url}/loraData?data_type=posData")
    if not payload:
        return None
    try:
        state = payload["data"]
        if not isinstance(state, (list, tuple)) or len(state) < 6:
            raise ValueError("LoRa GV state must contain six fields")
        mission_id = _mission_id(state[5])
        position = tuple(float(value) for value in state[0:2])
        yaw_degrees = float(state[2])
        sensed_at = float(state[3])
        height = float(state[4])
        velocity = (
            tuple(float(value) for value in state[6:8])
            if len(state) >= 8
            else None
        )
        if not all(
            math.isfinite(value)
            for value in (
                *position,
                yaw_degrees,
                sensed_at,
                height,
                *(() if velocity is None else velocity),
            )
        ):
            raise ValueError("LoRa GV state values must be finite")
        return {
            "mission_id": mission_id,
            "sample_id": (mission_id, sensed_at),
            "position": position,
            "yaw_degrees": yaw_degrees,
            "height": height,
            "velocity": velocity,
            "sensed_at": sensed_at,
        }
    except (KeyError, IndexError, TypeError, ValueError) as error:
        log.error(f"      [requests]invalid LoRa GV state: {error}")
        return None


def get_lora_link_status(url, timeout=0.3):
    """Return whether a real LoRa frame arrived within the heartbeat timeout."""
    timeout = float(timeout)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a positive finite value")
    payload = _get_json(
        f"{url}/loraLinkStatus?data_type=posData&timeout={timeout}"
    )
    if not payload:
        return False
    healthy = payload.get("healthy")
    if not isinstance(healthy, bool):
        log.error("      [requests]invalid LoRa link status")
        return False
    return healthy


def get_follow_config(url):
    """Return remotely configured D/H values, if available."""
    payload = _get_json(f"{url}/checkDH")
    if not payload:
        return None
    try:
        guiding_range = float(payload["D"])
        height = float(payload["H"])
        if (
            not math.isfinite(guiding_range)
            or not math.isfinite(height)
            or guiding_range < 0
            or guiding_range > 100
            or height <= 0
            or height > 120
        ):
            raise ValueError(
                "D must be in [0, 100] m and H must be in (0, 120] m"
            )
        return {"guiding_range": guiding_range, "height": height}
    except (KeyError, TypeError, ValueError) as error:
        log.error(f"      [requests]invalid D/H configuration: {error}")
        return None


def get_mission_id(url):
    payload = _get_json(f"{url}/curTimeStr")
    if not payload:
        return None
    try:
        return _mission_id(payload["time_str"])
    except (KeyError, TypeError, ValueError):
        return None


def get_height(url):
    """Read one height sample with its original sensing timestamp."""
    payload = _get_json(f"{url}/height")
    if not payload:
        return None
    try:
        mission_id = _mission_id(payload["mission_id"])
        height = float(payload["height"])
        sensed_at = float(payload["time"])
        if not math.isfinite(height) or not math.isfinite(sensed_at):
            raise ValueError("height and time must be finite")
        return {
            "mission_id": mission_id,
            "height": height,
            "sensed_at": sensed_at,
        }
    except (KeyError, TypeError, ValueError) as error:
        log.error(f"      [requests]invalid UAV height state: {error}")
        return None


def get_origin_pos(url):
    payload = _get_json(f"{url}/originPos")
    if not payload:
        return None
    try:
        latitude = float(payload["latitude"])
        return latitude if math.isfinite(latitude) else None
    except (KeyError, TypeError, ValueError):
        return None


def get_origin_height(url):
    payload = _get_json(f"{url}/originHeight")
    if not payload:
        return None
    try:
        height = float(payload["height"])
        return height if math.isfinite(height) else None
    except (KeyError, TypeError, ValueError):
        return None


def set_uav_control_input(url, vx, vy, vz, yaw):
    """Send an ENU command through the DJI north/east ground-frame API."""
    east_velocity = float(vx)
    north_velocity = float(vy)
    compass_heading = (90.0 - float(yaw) + 180.0) % 360.0 - 180.0
    url = (
        f"{url}/setUavControl"
        f"?vx={north_velocity}&vy={east_velocity}"
        f"&vz={vz}&yaw={compass_heading}"
    )
    re = get(url)
    if re and re.status_code == 200:
        return True
    else:
        return False


def set_uav_control_input_cmd(url, cmd):
    url = f"{url}/setUavControlCmd?cmd={cmd}"
    re = get(url, timeout=0.5)
    if re and re.status_code == 200:
        return True
    else:
        return False


def set_mission_state(
    url,
    mission_id,
    phase,
    active_source=None,
    airborne=None,
):
    """Publish controller-confirmed mission state to the remote API."""
    payload = {
        "mission_id": _mission_id(mission_id),
        "phase": str(phase),
        "active_source": active_source,
        "airborne": airborne,
    }
    try:
        response = requests.post(
            f"{url}/missionState",
            json=payload,
            timeout=0.5,
        )
    except Exception as error:
        log.error(
            f"      [requests]{url}/missionState request failed, error: "
            f"{error}"
        )
        return False
    return 200 <= response.status_code < 300


def check_depart(url):
    """Return the remote mission order as True, False, or None.

    The current remote API uses HTTP 403 to represent an explicit inactive
    mission. Transport failures and unexpected responses are unknown states;
    callers must retain the last valid order rather than interpreting them as
    a landing request.
    """
    request_url = f"{url}/depart"
    response = get(request_url, timeout=0.5)
    if response is None:
        return None
    if response.status_code == 403:
        return False
    if response.status_code != 200:
        log.error(
            f"      [requests]{request_url} returned unexpected status "
            f"{response.status_code}"
        )
        return None
    try:
        depart_flag = response.json()["depart_flag"]
    except (KeyError, TypeError, ValueError) as error:
        log.error(
            f"      [requests]{request_url} returned invalid depart state: "
            f"{error}"
        )
        return None
    if not isinstance(depart_flag, bool):
        log.error(
            f"      [requests]{request_url} depart_flag must be boolean"
        )
        return None
    return depart_flag


def check_emergency_stop(url):
    """Return emergency-stop state as True, False, or None."""
    request_url = f"{url}/emergencyStop"
    response = get(request_url, timeout=0.5)
    if response is None:
        return None
    if response.status_code == 403:
        return False
    if response.status_code != 200:
        log.error(
            f"      [requests]{request_url} returned unexpected status "
            f"{response.status_code}"
        )
        return None
    try:
        emergency_stop = response.json()["emergency_stop_flag"]
    except (KeyError, TypeError, ValueError) as error:
        log.error(
            f"      [requests]{request_url} returned invalid emergency state: "
            f"{error}"
        )
        return None
    if not isinstance(emergency_stop, bool):
        log.error(
            f"      [requests]{request_url} emergency_stop_flag must be "
            "boolean"
        )
        return None
    return emergency_stop
