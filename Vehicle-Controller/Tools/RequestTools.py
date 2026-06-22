import requests
import Tools.LogUtil as log


def get(url, timeout=0.5):
    try:
        re = requests.get(url, timeout=timeout)
        return re
    except Exception as e:
        log.error(f"      [requests]{url}request failed, error: {e}")
        return None


def get_pos(url):
    url = f"{url}/pos"
    re = get(url)
    if re and re.status_code == 200:
        json = re.json()
        return json
    else:
        return None


def get_pos_remote(url):
    url = f"{url}/ugvPos"
    re = get(url)
    if re and re.status_code == 200:
        json = re.json()
        return json
    else:
        return None


def get_height(url):
    url = f"{url}/height"
    re = get(url)
    if re and re.status_code == 200:
        json = re.json()
        return json["height"]
    else:
        return None


def get_origin_pos(url):
    url = f"{url}/originPos"
    re = get(url)
    if re and re.status_code == 200:
        json = re.json()
        return json["latitude"]
    else:
        return None


def get_origin_height(url):
    url = f"{url}/originHeight"
    re = get(url)
    if re and re.status_code == 200:
        json = re.json()
        return json["height"]
    else:
        return None


def set_uav_control_input(url, vx, vy, vz, yaw):
    url = f"{url}/setUavControl?vx={vx}&vy={vy}&vz={vz}&yaw={yaw}"
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


def check_depart(url):
    url = f"{url}/depart"
    re = get(url, timeout=0.5)
    if re and re.status_code == 200:
        return True
    else:
        return False
