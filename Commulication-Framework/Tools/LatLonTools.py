from geopy.distance import great_circle as grc


def transform_to_xygen(origin_latitude, origin_longitude, current_latitude, current_longitude):
    """Return local ENU planar coordinates as ``[east, north]`` in metres."""
    origin = (origin_latitude, origin_longitude)
    target_point = (current_latitude, current_longitude)

    x_distance = grc(origin, (origin[0], target_point[1])).m
    y_distance = grc(origin, (target_point[0], origin[1])).m

    if target_point[1] < origin[1]:
        x_distance = -x_distance

    if target_point[0] < origin[0]:
        y_distance = -y_distance

    return [x_distance, y_distance]


def check_distance(a_latitude, a_longitude, b_latitude, b_longitude, threshold):
    return grc((a_latitude, a_longitude), (b_latitude, b_longitude)).m <= threshold


def distance(a_latitude, a_longitude, b_latitude, b_longitude):
    return grc((a_latitude, a_longitude), (b_latitude, b_longitude)).m
