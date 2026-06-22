from datetime import datetime


def time_str():
    time_format = "%y-%m-%d %H:%M:%S"
    return datetime.now().strftime(time_format)


def warn(info_str):
    print(f"[{time_str()}] {info_str} ⚠", flush=True)


def info(info_str):
    print(f"[{time_str()}] {info_str} ☐", flush=True)


def error(info_str):
    print(f"[{time_str()}] {info_str} ☒", flush=True)


def success(info_str):
    print(f"[{time_str()}] {info_str} ☑", flush=True)