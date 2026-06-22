#include "application.hpp"
#include <dji_logger.h>

#include "../fly_controller/fly_control_main.h"
#include "dji_logger.h"

#include <vector>
#include <string>

int main(int argc, char **argv)
{
    Application application(argc, argv);
    USER_LOG_INFO("[Main] App started successfully");
    MainFlyControlLoop();
    USER_LOG_INFO("[Main] App exited successfully");
    return 0;
}

