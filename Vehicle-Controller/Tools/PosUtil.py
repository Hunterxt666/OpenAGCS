import math


def resolve_pos_data(name, msg):
    idx = msg.name.index(name)
    pos = msg.pose[idx].position
    angles = msg.pose[idx].orientation
    x, y, z, w = angles.x, angles.y, angles.z, angles.w
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return [pos.x, pos.y, pos.z, yaw]

def distance(a, b):
    re = 0
    for i in range(len(a)):
        re += (a[i]-b[i])**2
    return re ** 0.5