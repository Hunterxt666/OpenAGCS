import requests
from urllib.parse import quote_plus
from Tools.TimeUtils import transform_to_str
import Tools.LogUtils as log

def get(url, timeout=0.5):
    try:
        return requests.get(url, timeout=timeout)
    except Exception as e:
        log.error(f"                  [requests] GET {url} error: {e}")
        return None

def post(url, json, timeout=0.5):
    try:
        return requests.post(url, json=json, timeout=timeout)
    except Exception as e:
        log.error(f"                  [requests] POST {url} error: {e}")
        return None

def post_files(url, files, timeout=0.5):
    try:
        return requests.post(url, files=files, timeout=timeout)
    except Exception as e:
        log.error(f"                  [requests] POST {url} error: {e}")
        return None


def send_photo(url, path, time):
    url = f"{url}/uavUploadPhoto?time={time}"
    with open(path, "rb") as file:
        files = {"file": file}
        post_files(url, files=files, timeout=2)

def send_ugv_photo(url, path, time):
    url = f"{url}/ugvUploadPhoto?time={time}"
    with open(path, "rb") as file:
        files = {"file": file}
        post_files(url, files=files, timeout=2)


def send_photo_path(url, path, time):
    url = f"{url}/updatePhotoPath?time={time}&path={path}"
    get(url, timeout=1)


def send_time_str(url, time_str):
    url = f"{url}/setTimeStr?time_string={time_str}"
    re = get(url, timeout=0.5)
    if re is not None and re.status_code == 200:
        return True
    else:
        return False


def get_time_str(url):
    url = f"{url}/curTimeStr"
    re =  get(url, timeout=0.5)
    if re is not None and re.status_code == 200:
        return re.json()
    return None


def send_clean_str(url):
    url = f"{url}/cleanTimeStr"
    get(url, timeout=0.5)


def _mission_query(mission_id):
    return (
        ""
        if mission_id is None
        else f"&mission_id={quote_plus(str(mission_id))}"
    )


def send_pos(url, longitude, latitude, time, agent, mission_id=None):
    url = f"{url}/updatePos?latitude={latitude}&longitude={longitude}&time={transform_to_str(time)}&agent={agent}"
    url += _mission_query(mission_id)
    response = get(url, timeout=0.5)
    return response is not None and 200 <= response.status_code < 300


def send_height(url, time, height, agent, mission_id=None):
    url = f"{url}/updateHeight?height={height}&time={transform_to_str(time)}&agent={agent}"
    url += _mission_query(mission_id)
    response = get(url, timeout=0.5)
    return response is not None and 200 <= response.status_code < 300


def send_orientation(url, time, orientation, agent, mission_id=None):
    url = f"{url}/setOrientation?orientation={orientation}&time={transform_to_str(time)}&agent={agent}"
    url += _mission_query(mission_id)
    response = get(url, timeout=0.5)
    return response is not None and 200 <= response.status_code < 300

    
def set_origin_pos(url):
    url = f"{url}/setOriginPos"
    re = get(url, timeout=3)
    if  re is not None and re.status_code == 200:
        return re.json()
    return None


def get_origin_pos(url):
    url = f"{url}/originPos"
    re = get(url, timeout=3)
    if  re is not None and re.status_code == 200:
        return re.json()
    return None


def set_local_origin_pos(url, latitude, longitude, height, time):
    url = f"{url}/setOriginPos?latitude={latitude}&longitude={longitude}&height={height}&time={time}"
    get(url, timeout=0.5)


def get_raw_msg(url, loc):
    url = f"{url}/{loc}"
    re = get(url, timeout=0.5)
    if re is not None and re.status_code == 200:
        return re.json()[loc]
    return None


def send_lora_data(url, data_type, data, received_at=None):
    url = f"{url}/setLoraData"
    payload = {"data_type": data_type, "data": data}
    if received_at is not None:
        payload["received_at"] = float(received_at)
    response = post(
        url,
        json=payload,
        timeout=1,
    )
    return response is not None and 200 <= response.status_code < 300
