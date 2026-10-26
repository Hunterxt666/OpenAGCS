from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd


NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
WALL_RE = re.compile(
    r"\[(?P<ts>\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\]"
)
TASK_RE = re.compile(
    rf"开始跟随任务，初始D->\s*(?P<d>{NUMBER})\s*,\s*"
    rf"初始h->\s*(?P<h>{NUMBER})(?:\s*,\s*时间->\s*(?P<t>{NUMBER}))?"
)
POSITION_RE = re.compile(
    rf"Distance\s*->\s*(?P<distance>{NUMBER})\s+"
    rf"Height\s*->\s*(?P<height>{NUMBER})\s+"
    rf"UAV\s*-\s*>\s*\[\s*(?P<uav_x>{NUMBER})\s*,\s*"
    rf"(?P<uav_y>{NUMBER})\s*,\s*(?P<uav_z>{NUMBER})\s*\]\s+"
    rf"UGV\s*->\s*\[\s*(?P<ugv_x>{NUMBER})\s*,\s*"
    rf"(?P<ugv_y>{NUMBER})\s*\]\s+"
    rf"UAV_yaw\s*->\s*(?P<uav_yaw>{NUMBER})degree\s+"
    rf"UGV_yaw\s*->\s*(?P<ugv_yaw>{NUMBER})degree"
)
DELTA_RE = re.compile(
    rf"delta_x\s*(?P<x>{NUMBER})\s*m,\s*"
    rf"delta_y\s*(?P<y>{NUMBER})\s*m,\s*"
    rf"delta_z\s*(?P<z>{NUMBER})\s*m"
    rf"(?:,\s*tmp_yaw_degree\s*(?P<tmp_yaw>{NUMBER})\s*degree)?"
)
REALTIME_RE = re.compile(
    rf"(?P<kind>UAV|UGV)实时位置:\[\s*(?P<x>{NUMBER})\s*,\s*"
    rf"(?P<y>{NUMBER})\s*,\s*(?P<z>{NUMBER})\s*\],\s*"
    rf"time:(?P<t>{NUMBER}),\s*yaw:(?P<yaw>{NUMBER})"
)
REMOTE_POS_RE = re.compile(
    rf"从远端更新ugv实时位置成功\s*(?P<x>{NUMBER})\s*,\s*"
    rf"(?P<y>{NUMBER})\s*,\s*cur_time\s*(?P<t>{NUMBER})"
)
REMOTE_YAW_RE = re.compile(
    rf"从远端更新ugv实时yaw成功\s*(?P<yaw>{NUMBER})\s*,\s*"
    rf"cur_time\s*(?P<t>{NUMBER})"
)
LORA_RE = re.compile(
    rf"从LoRa获取ugv实时位置成功(?:\[\s*)?"
    rf"(?P<x>{NUMBER})\s*,\s*(?P<y>{NUMBER})"
    rf"(?:\s*,\s*(?P<z>{NUMBER}))?(?:\s*\])?\s*,\s*"
    rf"yaw\s*->\s*(?P<yaw>{NUMBER})\s*,\s*cur_time\s*(?P<t>{NUMBER})"
)
STATE_AGE_RE = re.compile(
    rf"获取ugv实时\(差\s*(?P<age>{NUMBER})s\)位置成功.*?"
    rf"uav_t\s*(?P<uav_t>{NUMBER})\s*,\s*ugv_t\s*(?P<ugv_t>{NUMBER})"
)
PAYLOAD_RE = re.compile(r"re ->\s*(\{.*?\})(?:\s|$)")
UAV_UPDATE_POS_RE = re.compile(
    rf"/updatePos\?[^\" ]*latitude=(?P<latitude>{NUMBER})"
    rf"&longitude=(?P<longitude>{NUMBER})"
    rf"&time=(?P<time>{NUMBER})&agent=UAV"
)


def parse_wall_time(line: str) -> datetime | None:
    match = WALL_RE.search(line)
    if not match:
        return None
    text = match.group("ts")
    for fmt in ("%y-%m-%d %H:%M:%S.%f", "%y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def payload_from_line(line: str) -> dict | None:
    match = PAYLOAD_RE.search(line)
    if not match:
        return None
    try:
        payload = ast.literal_eval(match.group(1))
    except (SyntaxError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def frame(rows: list[dict], sort_by: list[str] | None = None) -> pd.DataFrame:
    result = pd.DataFrame(rows)
    if result.empty or not sort_by:
        return result
    return result.sort_values(sort_by, kind="stable").reset_index(drop=True)


@dataclass
class ControllerLog:
    path: Path
    first_wall: datetime
    last_wall: datetime
    origin_wall: datetime | None
    takeoff_wall: datetime | None
    tasks: pd.DataFrame
    task_ends: pd.DataFrame
    positions: pd.DataFrame
    deltas: pd.DataFrame
    realtime_uav: pd.DataFrame
    realtime_ugv: pd.DataFrame
    remote_pos: pd.DataFrame
    remote_yaw: pd.DataFrame
    lora: pd.DataFrame
    state_age: pd.DataFrame
    payload_uav: pd.DataFrame
    payload_ugv_pos: pd.DataFrame
    payload_ugv_yaw: pd.DataFrame
    geo_uav: pd.DataFrame
    geo_ugv: pd.DataFrame

    @property
    def duration_s(self) -> float:
        return (self.last_wall - self.first_wall).total_seconds()


CONTROLLER_RECORD_TYPES = (
    "tasks",
    "task_ends",
    "positions",
    "deltas",
    "realtime_uav",
    "realtime_ugv",
    "remote_pos",
    "remote_yaw",
    "lora",
    "state_age",
    "payload_uav",
    "payload_ugv_pos",
    "payload_ugv_yaw",
    "geo_uav",
    "geo_ugv",
)

CONTROLLER_METADATA_COLUMNS = (
    "metadata_first_wall",
    "metadata_last_wall",
    "metadata_origin_wall",
    "metadata_takeoff_wall",
)

UAV_GEO_COLUMNS = (
    "line_idx",
    "wall_time",
    "wall_elapsed_s",
    "state_time_s",
    "longitude_deg",
    "latitude_deg",
)


def parse_controller_log(path: Path) -> ControllerLog:
    tasks: list[dict] = []
    task_ends: list[dict] = []
    positions: list[dict] = []
    deltas: list[dict] = []
    realtime_uav: list[dict] = []
    realtime_ugv: list[dict] = []
    remote_pos: list[dict] = []
    remote_yaw: list[dict] = []
    lora: list[dict] = []
    state_age: list[dict] = []
    payload_uav: list[dict] = []
    payload_ugv_pos: list[dict] = []
    payload_ugv_yaw: list[dict] = []
    geo_uav: list[dict] = []
    geo_ugv: list[dict] = []

    first_wall: datetime | None = None
    last_wall: datetime | None = None
    origin_wall: datetime | None = None
    takeoff_wall: datetime | None = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_idx, line in enumerate(handle):
            wall = parse_wall_time(line)
            if wall is None:
                continue
            if first_wall is None:
                first_wall = wall
            last_wall = wall
            wall_s = (wall - first_wall).total_seconds()
            base = {
                "line_idx": line_idx,
                "wall_time": wall,
                "wall_elapsed_s": wall_s,
            }

            if origin_wall is None and "原点设置成功，进入主循环" in line:
                origin_wall = wall
            if takeoff_wall is None and re.search(
                r"Execute\s+TAKEOFF\s+successfully", line, re.I
            ):
                takeoff_wall = wall

            match = TASK_RE.search(line)
            if match:
                tasks.append(
                    {
                        **base,
                        "desired_d_m": float(match.group("d")),
                        "desired_h_m": float(match.group("h")),
                        "state_time_s": (
                            float(match.group("t")) if match.group("t") else None
                        ),
                    }
                )
            if "结束跟随任务" in line and "DroneAgent" in line:
                task_ends.append(base.copy())

            match = POSITION_RE.search(line)
            if match:
                positions.append(
                    {
                        **base,
                        **{
                            name: float(match.group(group))
                            for name, group in (
                                ("distance_m", "distance"),
                                ("height_m", "height"),
                                ("uav_x_m", "uav_x"),
                                ("uav_y_m", "uav_y"),
                                ("uav_z_m", "uav_z"),
                                ("ugv_x_m", "ugv_x"),
                                ("ugv_y_m", "ugv_y"),
                                ("uav_yaw_deg", "uav_yaw"),
                                ("ugv_yaw_deg", "ugv_yaw"),
                            )
                        },
                    }
                )

            match = DELTA_RE.search(line)
            if match:
                deltas.append(
                    {
                        **base,
                        "delta_x_m": float(match.group("x")),
                        "delta_y_m": float(match.group("y")),
                        "delta_z_m": float(match.group("z")),
                        "tmp_yaw_deg": (
                            float(match.group("tmp_yaw"))
                            if match.group("tmp_yaw")
                            else None
                        ),
                    }
                )

            match = REALTIME_RE.search(line)
            if match:
                record = {
                    **base,
                    "state_time_s": float(match.group("t")),
                    "x_m": float(match.group("x")),
                    "y_m": float(match.group("y")),
                    "z_m": float(match.group("z")),
                    "yaw": float(match.group("yaw")),
                }
                if match.group("kind") == "UAV":
                    realtime_uav.append(record)
                else:
                    realtime_ugv.append(record)

            match = REMOTE_POS_RE.search(line)
            if match:
                remote_pos.append(
                    {
                        **base,
                        "state_time_s": float(match.group("t")),
                        "x_m": float(match.group("x")),
                        "y_m": float(match.group("y")),
                    }
                )

            match = REMOTE_YAW_RE.search(line)
            if match:
                remote_yaw.append(
                    {
                        **base,
                        "state_time_s": float(match.group("t")),
                        "yaw_rad": float(match.group("yaw")),
                    }
                )

            match = LORA_RE.search(line)
            if match:
                lora.append(
                    {
                        **base,
                        "state_time_s": float(match.group("t")),
                        "x_m": float(match.group("x")),
                        "y_m": float(match.group("y")),
                        "z_m": (
                            float(match.group("z")) if match.group("z") else None
                        ),
                        "yaw_deg_packet": float(match.group("yaw")),
                    }
                )

            match = STATE_AGE_RE.search(line)
            if match:
                state_age.append(
                    {
                        **base,
                        "age_s": float(match.group("age")),
                        "uav_time_s": float(match.group("uav_t")),
                        "ugv_time_s": float(match.group("ugv_t")),
                    }
                )

            payload = payload_from_line(line)
            if payload is None:
                continue
            state_time = payload.get("time")
            pos = payload.get("current_pos")
            if (
                "http://127.0.0.1:26969/pos" in line
                and state_time is not None
                and isinstance(pos, (list, tuple))
                and len(pos) >= 2
            ):
                payload_uav.append(
                    {
                        **base,
                        "state_time_s": float(state_time),
                        "x_m": float(pos[0]),
                        "y_m": float(pos[1]),
                    }
                )
            elif (
                "ugvPos" in line
                and state_time is not None
                and isinstance(pos, (list, tuple))
                and len(pos) >= 2
            ):
                payload_ugv_pos.append(
                    {
                        **base,
                        "state_time_s": float(state_time),
                        "x_m": float(pos[0]),
                        "y_m": float(pos[1]),
                    }
                )
            elif (
                "ugvOrientation" in line
                and state_time is not None
                and "ugv_orientation" in payload
            ):
                # This sign conversion is the ENU convention used by the paper's
                # original outer-loop reconstruction notebook.
                yaw_deg = -float(payload["ugv_orientation"])
                payload_ugv_yaw.append(
                    {
                        **base,
                        "state_time_s": float(state_time),
                        "yaw_deg": yaw_deg,
                    }
                )

            longitude = payload.get("longitude")
            latitude = payload.get("latitude")
            if longitude is None or latitude is None or state_time is None:
                continue
            geo_record = {
                **base,
                "state_time_s": float(state_time),
                "longitude_deg": float(longitude),
                "latitude_deg": float(latitude),
            }
            if "ugvPos" in line:
                geo_ugv.append(geo_record)
            elif "/pos" in line:
                geo_uav.append(geo_record)

    if first_wall is None or last_wall is None:
        raise ValueError(f"No timestamped records in {path}")

    origin = origin_wall or first_wall
    for rows in (
        tasks,
        task_ends,
        positions,
        deltas,
        realtime_uav,
        realtime_ugv,
        remote_pos,
        remote_yaw,
        lora,
        state_age,
        payload_uav,
        payload_ugv_pos,
        payload_ugv_yaw,
        geo_uav,
        geo_ugv,
    ):
        for row in rows:
            row["mission_wall_s"] = (row["wall_time"] - origin).total_seconds()

    return ControllerLog(
        path=path,
        first_wall=first_wall,
        last_wall=last_wall,
        origin_wall=origin_wall,
        takeoff_wall=takeoff_wall,
        tasks=frame(tasks, ["wall_elapsed_s"]),
        task_ends=frame(task_ends, ["wall_elapsed_s"]),
        positions=frame(positions, ["wall_elapsed_s"]),
        deltas=frame(deltas, ["wall_elapsed_s"]),
        realtime_uav=frame(realtime_uav, ["state_time_s", "line_idx"]),
        realtime_ugv=frame(realtime_ugv, ["state_time_s", "line_idx"]),
        remote_pos=frame(remote_pos, ["state_time_s", "line_idx"]),
        remote_yaw=frame(remote_yaw, ["state_time_s", "line_idx"]),
        lora=frame(lora, ["state_time_s", "line_idx"]),
        state_age=frame(state_age, ["wall_elapsed_s"]),
        payload_uav=frame(payload_uav, ["state_time_s", "line_idx"]),
        payload_ugv_pos=frame(payload_ugv_pos, ["state_time_s", "line_idx"]),
        payload_ugv_yaw=frame(payload_ugv_yaw, ["state_time_s", "line_idx"]),
        geo_uav=frame(geo_uav, ["state_time_s", "line_idx"]),
        geo_ugv=frame(geo_ugv, ["state_time_s", "line_idx"]),
    )


def export_controller_csv(log: ControllerLog, path: Path) -> None:
    """Export every parsed controller record and its time basis to one CSV."""
    metadata = pd.DataFrame(
        [
            {
                "record_type": "metadata",
                "metadata_first_wall": log.first_wall.isoformat(),
                "metadata_last_wall": log.last_wall.isoformat(),
                "metadata_origin_wall": (
                    log.origin_wall.isoformat() if log.origin_wall else None
                ),
                "metadata_takeoff_wall": (
                    log.takeoff_wall.isoformat() if log.takeoff_wall else None
                ),
            }
        ]
    )
    records = [metadata]
    for record_type in CONTROLLER_RECORD_TYPES:
        data = getattr(log, record_type)
        if data.empty:
            continue
        exported = data.copy()
        exported.insert(0, "record_type", record_type)
        records.append(exported)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(records, ignore_index=True, sort=False).to_csv(
        path,
        index=False,
        float_format="%.12g",
    )


def load_controller_csv(path: Path) -> ControllerLog:
    """Load the publishable CSV representation of one controller trial."""
    data = pd.read_csv(path, low_memory=False)
    if "record_type" not in data:
        raise ValueError(f"Missing record_type column in {path}")
    metadata = data[data["record_type"] == "metadata"]
    if len(metadata) != 1:
        raise ValueError(f"Expected one metadata row in {path}")
    metadata = metadata.iloc[0]

    def metadata_time(column: str, required: bool = False):
        value = metadata.get(column)
        if pd.isna(value):
            if required:
                raise ValueError(f"Missing {column} in {path}")
            return None
        return pd.Timestamp(value).to_pydatetime()

    frames = {}
    for record_type in CONTROLLER_RECORD_TYPES:
        selected = data[data["record_type"] == record_type].copy()
        selected = selected.drop(
            columns=["record_type", *CONTROLLER_METADATA_COLUMNS],
            errors="ignore",
        ).dropna(axis=1, how="all")
        if "wall_time" in selected:
            selected["wall_time"] = pd.to_datetime(selected["wall_time"])
        if "line_idx" in selected:
            selected["line_idx"] = selected["line_idx"].astype(int)
        frames[record_type] = selected.reset_index(drop=True)

    return ControllerLog(
        path=path,
        first_wall=metadata_time("metadata_first_wall", required=True),
        last_wall=metadata_time("metadata_last_wall", required=True),
        origin_wall=metadata_time("metadata_origin_wall"),
        takeoff_wall=metadata_time("metadata_takeoff_wall"),
        **frames,
    )


def parse_controller_input(path: Path) -> ControllerLog:
    """Load a released CSV trial or parse an internal archived log."""
    if path.suffix.lower() == ".csv":
        return load_controller_csv(path)
    return parse_controller_log(path)


def parse_uav_geo_log(path: Path) -> pd.DataFrame:
    rows: list[dict] = []
    first_wall: datetime | None = None
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_idx, line in enumerate(handle):
            update_match = UAV_UPDATE_POS_RE.search(line)
            wall = parse_wall_time(line)
            if wall is None and update_match:
                source_time = update_match.group("time")
                if len(source_time) == 20 and source_time.isdigit():
                    wall = datetime.strptime(source_time, "%Y%m%d%H%M%S%f")
            payload = payload_from_line(line)
            if wall is None:
                continue
            if first_wall is None:
                first_wall = wall
            wall_elapsed_s = (wall - first_wall).total_seconds()
            if (
                payload is not None
                and all(
                    key in payload
                    for key in ("longitude", "latitude", "time")
                )
                and "/pos" in line
            ):
                rows.append(
                    {
                        "line_idx": line_idx,
                        "wall_time": wall,
                        "wall_elapsed_s": wall_elapsed_s,
                        "state_time_s": float(payload["time"]),
                        "longitude_deg": float(payload["longitude"]),
                        "latitude_deg": float(payload["latitude"]),
                    }
                )
                continue

            # The standalone UAV log records the same upload as an HTTP
            # access line rather than as a parsed JSON response.
            if update_match:
                rows.append(
                    {
                        "line_idx": line_idx,
                        "wall_time": wall,
                        "wall_elapsed_s": wall_elapsed_s,
                        "state_time_s": wall_elapsed_s,
                        "longitude_deg": float(
                            update_match.group("longitude")
                        ),
                        "latitude_deg": float(
                            update_match.group("latitude")
                        ),
                    }
                )
    return frame(rows, ["state_time_s", "line_idx"])


def load_uav_geo_csv(path: Path) -> pd.DataFrame:
    try:
        data = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=UAV_GEO_COLUMNS)
    if "wall_time" in data:
        data["wall_time"] = pd.to_datetime(data["wall_time"])
    if "line_idx" in data:
        data["line_idx"] = data["line_idx"].astype(int)
    return frame(data.to_dict(orient="records"), ["state_time_s", "line_idx"])


def parse_uav_geo_input(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return load_uav_geo_csv(path)
    return parse_uav_geo_log(path)


def deduplicate_state(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    return (
        df.sort_values(["state_time_s", "line_idx"], kind="stable")
        .drop_duplicates("state_time_s", keep="last")
        .reset_index(drop=True)
    )
