#ifndef UAV_EXECUTOR_YAW_ANGLE_UTILS_H
#define UAV_EXECUTOR_YAW_ANGLE_UTILS_H

#include <cmath>

namespace uav_executor {

// Normalize an angle to the half-open DJI yaw range [-180, 180).
inline double NormalizeYawAngle(double angle)
{
    double normalized = std::fmod(angle + 180.0, 360.0);
    if (normalized < 0.0) {
        normalized += 360.0;
    }
    return normalized - 180.0;
}

// Return the signed shortest rotation from current to target. At the exact
// 180-degree tie, use -180 degrees so the result remains deterministic.
inline double ShortestYawDelta(double current, double target)
{
    return NormalizeYawAngle(target - current);
}

// Move an absolute yaw command toward target without crossing the long way
// around the +/-180-degree boundary.
inline double StepYawAngle(double current, double target, double maxStep)
{
    current = NormalizeYawAngle(current);
    target = NormalizeYawAngle(target);

    if (maxStep <= 0.0) {
        return current;
    }

    const double delta = ShortestYawDelta(current, target);
    if (std::fabs(delta) <= maxStep) {
        return target;
    }

    const double signedStep = delta > 0.0 ? maxStep : -maxStep;
    return NormalizeYawAngle(current + signedStep);
}

} // namespace uav_executor

#endif // UAV_EXECUTOR_YAW_ANGLE_UTILS_H
