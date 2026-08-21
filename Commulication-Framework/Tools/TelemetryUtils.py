"""Helpers for constructing timestamp-consistent telemetry packets."""

import math
from numbers import Real


MIN_GUIDING_DISTANCE_M = 0.0
MAX_GUIDING_DISTANCE_M = 100.0
MIN_FLIGHT_HEIGHT_M = 0.0
MAX_FLIGHT_HEIGHT_M = 120.0


def normalize_degrees(angle):
    """Normalize an angle to the half-open interval [-180, 180)."""
    angle = _finite_number(angle, "angle")
    return (angle + 180.0) % 360.0 - 180.0


def compass_heading_to_enu_yaw(heading):
    """Convert clockwise-from-north sensor heading to ENU yaw."""
    return normalize_degrees(90.0 - _finite_number(heading, "heading"))


def derive_planar_velocity(
    previous_position,
    previous_time,
    current_position,
    current_time,
):
    """Derive ENU planar velocity, returning zero until two samples exist."""
    try:
        if (
            previous_position is None
            or current_position is None
            or len(previous_position) < 2
            or len(current_position) < 2
        ):
            raise ValueError
        previous = [
            _finite_number(previous_position[0], "previous_position[0]"),
            _finite_number(previous_position[1], "previous_position[1]"),
        ]
        current = [
            _finite_number(current_position[0], "current_position[0]"),
            _finite_number(current_position[1], "current_position[1]"),
        ]
        previous_time = _mission_relative_time(
            previous_time, "previous_time"
        )
        current_time = _mission_relative_time(current_time, "current_time")
        delta_time = current_time - previous_time
        if delta_time <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return [0.0, 0.0]
    return [
        (current[0] - previous[0]) / delta_time,
        (current[1] - previous[1]) / delta_time,
    ]


def normalize_mission_id(mission_id):
    """Return a stable string epoch identifier, or ``None`` when unavailable."""
    if mission_id is None or isinstance(mission_id, bool):
        return None
    normalized = str(mission_id).strip()
    return normalized or None


def _mission_relative_time(value, field_name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be mission-relative")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    if result < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return result


def _finite_number(value, field_name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


def build_position_heading_packet(
    position,
    yaw,
    location_time,
    yaw_time,
    mission_id,
    height=None,
    velocity=None,
):
    """Build a position/yaw packet timestamped by its oldest source field."""
    if (
        position is None
        or len(position) < 2
        or position[0] is None
        or position[1] is None
        or yaw is None
        or location_time is None
        or yaw_time is None
    ):
        raise ValueError("position and yaw samples are both required")
    mission_id = normalize_mission_id(mission_id)
    if mission_id is None:
        raise ValueError("mission_id is required")

    position_x = _finite_number(position[0], "position[0]")
    position_y = _finite_number(position[1], "position[1]")
    yaw = compass_heading_to_enu_yaw(yaw)
    position_time = _mission_relative_time(location_time, "location_time")
    heading_time = _mission_relative_time(yaw_time, "yaw_time")

    if height is not None:
        height = _finite_number(height, "height")
    if velocity is None:
        velocity = [0.0, 0.0]
    if not isinstance(velocity, (list, tuple)) or len(velocity) < 2:
        raise ValueError("velocity must contain east and north")
    east_velocity = _finite_number(velocity[0], "velocity[0]")
    north_velocity = _finite_number(velocity[1], "velocity[1]")

    return [
        position_x,
        position_y,
        yaw,
        min(position_time, heading_time),
        0 if height is None else height,
        mission_id,
        east_velocity,
        north_velocity,
    ]


def build_ugv_state(
    mission_id,
    current_pos,
    position_time,
    filtered_heading,
    heading_time,
    height=None,
    height_time=None,
    velocity=None,
    velocity_time=None,
):
    """Build one epoch-safe UGV state snapshot for controller consumption."""
    mission_id = normalize_mission_id(mission_id)
    if mission_id is None:
        raise ValueError("mission_id is required")
    if (
        current_pos is None
        or len(current_pos) < 2
        or current_pos[0] is None
        or current_pos[1] is None
        or filtered_heading is None
    ):
        raise ValueError("position and filtered heading are both required")

    position_x = _finite_number(current_pos[0], "current_pos[0]")
    position_y = _finite_number(current_pos[1], "current_pos[1]")
    filtered_heading = compass_heading_to_enu_yaw(
        filtered_heading
    )
    position_time = _mission_relative_time(position_time, "position_time")
    heading_time = _mission_relative_time(heading_time, "heading_time")
    if height is not None:
        height = _finite_number(height, "height")
    if height_time is not None:
        height_time = _mission_relative_time(height_time, "height_time")
    if velocity is not None:
        if not isinstance(velocity, (list, tuple)) or len(velocity) < 2:
            raise ValueError("velocity must contain east and north")
        velocity = [
            _finite_number(velocity[0], "velocity[0]"),
            _finite_number(velocity[1], "velocity[1]"),
        ]
    if velocity_time is not None:
        velocity_time = _mission_relative_time(
            velocity_time, "velocity_time"
        )
    return {
        "mission_id": mission_id,
        "current_pos": [position_x, position_y],
        "position_time": position_time,
        "filtered_heading": filtered_heading,
        "heading_time": heading_time,
        "height": height,
        "height_time": height_time,
        "current_velocity": velocity,
        "velocity_time": velocity_time,
        "sensed_at": min(position_time, heading_time),
    }


def validate_follow_parameters(guiding_distance, flight_height):
    """Validate the remotely configured follow distance and flight height."""
    guiding_distance = _finite_number(
        guiding_distance, "guiding_distance"
    )
    flight_height = _finite_number(flight_height, "flight_height")
    if not MIN_GUIDING_DISTANCE_M <= guiding_distance <= MAX_GUIDING_DISTANCE_M:
        raise ValueError(
            "guiding_distance must be in [0, 100] metres"
        )
    if not MIN_FLIGHT_HEIGHT_M < flight_height <= MAX_FLIGHT_HEIGHT_M:
        raise ValueError(
            "flight_height must be in (0, 120] metres"
        )
    return guiding_distance, flight_height
