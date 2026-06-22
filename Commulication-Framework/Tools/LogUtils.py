from datetime import datetime


def error(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]{msg}  ☒", flush=True)


def info(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]{msg} ☐", flush=True)


def warn(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]{msg} ⚠", flush=True)


def success(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]{msg} ☑", flush=True)

