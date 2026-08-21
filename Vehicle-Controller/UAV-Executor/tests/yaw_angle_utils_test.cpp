#include <cmath>
#include <cstdlib>
#include <iostream>

#include "../UAVcmd/fly_controller/yaw_angle_utils.h"

namespace {

void ExpectNear(double actual, double expected, const char *description)
{
    const double tolerance = 1e-9;
    if (std::fabs(actual - expected) > tolerance) {
        std::cerr << description << ": expected " << expected
                  << ", got " << actual << std::endl;
        std::exit(EXIT_FAILURE);
    }
}

} // namespace

int main()
{
    using uav_executor::NormalizeYawAngle;
    using uav_executor::ShortestYawDelta;
    using uav_executor::StepYawAngle;

    // Both representations of the boundary normalize identically.
    ExpectNear(NormalizeYawAngle(180.0), -180.0, "normalize +180");
    ExpectNear(NormalizeYawAngle(-180.0), -180.0, "normalize -180");
    ExpectNear(ShortestYawDelta(180.0, -180.0), 0.0,
               "equivalent boundary headings");

    // Crossing the boundary must take the two-degree path, not 358 degrees.
    ExpectNear(ShortestYawDelta(179.0, -179.0), 2.0,
               "positive boundary crossing delta");
    ExpectNear(StepYawAngle(179.0, -179.0, 1.5), -179.5,
               "positive boundary crossing step");
    ExpectNear(StepYawAngle(-179.5, -179.0, 1.5), -179.0,
               "positive boundary crossing target");

    ExpectNear(ShortestYawDelta(-179.0, 179.0), -2.0,
               "negative boundary crossing delta");
    ExpectNear(StepYawAngle(-179.0, 179.0, 1.5), 179.5,
               "negative boundary crossing step");
    ExpectNear(StepYawAngle(179.5, 179.0, 1.5), 179.0,
               "negative boundary crossing target");

    // The exact 180-degree tie has a stable, documented direction.
    ExpectNear(ShortestYawDelta(0.0, 180.0), -180.0,
               "exact half-turn tie");
    ExpectNear(StepYawAngle(0.0, 180.0, 30.0), -30.0,
               "exact half-turn step");

    std::cout << "yaw_angle_utils tests passed" << std::endl;
    return EXIT_SUCCESS;
}
