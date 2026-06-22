
/* Includes ------------------------------------------------------------------*/
#include <termios.h>
#include <string>
#include "../dji_utils/util_misc.h"
#include "../dji_utils/util_file.h"
#include "../dji_utils/cJSON.h"
#include <dji_aircraft_info.h>
#include "fly_control_main.h"
#include "dji_flight_controller.h"
#include "dji_logger.h"
#include "dji_fc_subscription.h"
#include "cmath"
#include "request_utils.h"

#ifdef OPEN_CV_INSTALLED

#include "opencv2/opencv.hpp"
#include "opencv2/highgui/highgui.hpp"

using namespace cv;
#endif

/* Private constants ---------------------------------------------------------*/
#define DJI_TEST_COMMAND_FLYING_TASK_STACK_SIZE                          2048
#define DJI_TEST_COMMAND_FLYING_CTRL_FREQ                                20
#define DJI_TEST_COMMAND_FLYING_GO_HOME_ALTITUDE                         50
#define DJI_TEST_COMMAND_FLYING_CONTROL_SPEED_DEFAULT                    0.1
#define DJI_TEST_COMMAND_FLYING_RC_LOST_ACTION_STR_MAX_LEN               32
#define DJI_TEST_COMMAND_FLYING_CONFIG_DIR_PATH_LEN_MAX                  (256)
#define MAX_X_SPEED                                                      10.0
#define MAX_Y_SPEED                                                      10.0
#define MAX_Z_SPEED                                                      5.0
#define MAX_ANGEL                                                        180.0
#define SEQ_FREQUENCY                                                    10.0
#define CMD_FREQUENCY                                                    5.0
#define SEQ_CHANGE_FREQUENCY                                             20.0
#define SEQ_SPEED_CHANGE_PER_SECONDS                                     2.0
#define SEQ_ANGEL_CHANGE_PER_SECONDS                                     30.0
#define CHECK_EMERGENCY_FREQUENCY                                        0.5


/* Private types -------------------------------------------------------------*/

/* Private values -------------------------------------------------------------*/
static T_DjiTaskHandle s_commandFlyingTaskHandle;
static T_DjiTaskHandle s_statusDisplayTaskHandle;
static T_DjiFlightControllerJoystickCommand s_flyingCommand = {0};
static uint16_t s_inputFlag = 0;
static dji_f32_t s_flyingSpeed = DJI_TEST_COMMAND_FLYING_CONTROL_SPEED_DEFAULT;
static uint16_t s_goHomeAltitude = DJI_TEST_COMMAND_FLYING_GO_HOME_ALTITUDE;
static char s_rcLostActionString[DJI_TEST_COMMAND_FLYING_RC_LOST_ACTION_STR_MAX_LEN] = {0};
static T_DjiFlightControllerHomeLocation s_homeLocation = {0};
static T_DjiFcSubscriptionGpsPosition s_gpsPosition = {0};
static bool isFirstUpdateConfig = false;

static bool suspendCtrlSeqCommand = true;
static bool suspendCtrlCmdCommand = true;
static bool stopCtrlSeqCommand = true;
static bool wait_yaw_to_publish = true;

static Control_seq cur_send_to_uav(0, 0, 0, 0, 0);

static uint32_t s_statusDisplayTaskCnt = 0;
static T_DjiFcSubscriptionSingleBatteryInfo singleBatteryInfo1 = {0};
static T_DjiFcSubscriptionSingleBatteryInfo singleBatteryInfo2 = {0};

/* Private functions declaration ---------------------------------------------*/
static void *DjiUser_FlightControllerCommandFlyingTask(void *arg);
static void *DjiUser_FlightControllerStatusDisplayTask(void *arg);
static void DjiUser_ShowFlightStatusByOpenCV(void);
static void DjiUser_FlightControllerVelocityAndYawRateCtrl(T_DjiFlightControllerJoystickCommand command);
static int DjiUser_ScanKeyboardInput(void);
static T_DjiReturnCode
DjiUser_FlightCtrlJoystickCtrlAuthSwitchEventCb(T_DjiFlightControllerJoystickCtrlAuthorityEventInfo eventData);
static T_DjiFcSubscriptionGpsPosition DjiUser_FlightControlGetValueOfGpsPosition(void);
static T_DjiFcSubscriptionAltitudeOfHomePoint DjiUser_FlightControlGetValueOfRelativeHeight(void);
static T_DjiFcSubscriptionPositionVO DjiUser_FlightControlGetValueOfPositionVo(void);

static T_DjiReturnCode DjiUser_FlightControlUpdateConfig(void);

const double speed_per_step = SEQ_SPEED_CHANGE_PER_SECONDS / SEQ_CHANGE_FREQUENCY;
const double angel_per_step = SEQ_ANGEL_CHANGE_PER_SECONDS / SEQ_CHANGE_FREQUENCY;

/* Exported functions definition ---------------------------------------------*/

static void Dji_set_stick(void){
    T_DjiFlightControllerJoystickMode joystickMode = {
        DJI_FLIGHT_CONTROLLER_HORIZONTAL_VELOCITY_CONTROL_MODE, // Set control mode for horizontal velocity (+/-30 m/s)
        DJI_FLIGHT_CONTROLLER_VERTICAL_VELOCITY_CONTROL_MODE, // Set control mode for vertical velocity (+/-5 m/s)
        DJI_FLIGHT_CONTROLLER_YAW_ANGLE_CONTROL_MODE, // Yaw angle referenced to ground frame; auto flight uses ground frame in this mode.
        DJI_FLIGHT_CONTROLLER_HORIZONTAL_GROUND_COORDINATE, // Ground coordinate frame
        DJI_FLIGHT_CONTROLLER_STABLE_CONTROL_MODE_ENABLE, // Stable control mode
    };
    
    DjiFlightController_SetJoystickMode(joystickMode);

    USER_LOG_INFO("DjiFlightController_SetJoystickMode, successfully!");
}

// Return velocity and yaw within limits
double get_arnge_speed(double oral_speed, double max_val)
{
    oral_speed = oral_speed >= max_val? max_val: oral_speed;
    oral_speed = oral_speed <= -max_val? -max_val: oral_speed;
    return oral_speed;
}

dji_f32_t change_speed(double range, double step, dji_f32_t cur, double max_val){
    if (range == cur){
        return cur;
    }
    double op = range >= cur ?  1.0:  -1.0;
    cur += op * step;
    if(range!=0 && abs(cur) - abs(range) > 0){
        cur = range;
    }
    else if(range==0 and abs(cur)>step){
        cur = range;
    }
    else{
        cur = get_arnge_speed(cur, max_val);
    }
    USER_LOG_INFO("      【change_speed】cur -> %.2f range-> %.2f",cur, range);
    return cur;
}

double resolve_to_360(double now){
    return now >= 360? now - 360 : now;
}


dji_f32_t change_angel(double target, double step, dji_f32_t cur){
    // target 179 cur 160 step 30
    // target -10 cur 10 step 30
    // target 170 cur 130 step 30
    if (abs(target - cur) <= 0.01){
        return cur;
    }
    target += 180; cur += 180;
    if(target > cur && target <= cur + step){
        cur = target;
    }
    else if(target < cur && target >= resolve_to_360(cur + step)){
        cur = target;
    }
    else{
        cur = resolve_to_360(cur + step);
    }
    USER_LOG_INFO("      【change_angel】cur -> %.2f target-> %.2f", cur - 180, target - 180);
    return cur - 180;
}

// void check_depart_ok(void){
//     T_DjiOsalHandler *osalHandler = DjiPlatform_GetOsalHandler();
//     dji_f32_t tmp = DjiUser_FlightControlGetValueOfRelativeHeight();
//     do
//     {
//         tmp = DjiUser_FlightControlGetValueOfRelativeHeight();
//         osalHandler -> TaskSleepMs(500 / CMD_FREQUENCY);
//     } while (abs(tmp - DjiUser_FlightControlGetValueOfRelativeHeight()) >= 0.1);
// }

static void * ExcuteCmd(void* arg){
    double time = 0;
    T_DjiOsalHandler *osalHandler = DjiPlatform_GetOsalHandler();
    USER_LOG_INFO("      [Command Listener] started");
    while(!suspendCtrlCmdCommand){
        Control_cmd cmd = get_ctrl_cmd();
        if(!cmd.is_empty && time != cmd.ctrl_time){
            stopCtrlSeqCommand = true;
            time = cmd.ctrl_time;
            USER_LOG_INFO("      [Command Listener] preparing to execute %s", cmd.cmd.c_str());
            if(cmd.cmd == "TAKEOFF"){ // takeoff
                DjiFlightController_ObtainJoystickCtrlAuthority();
                DjiFlightController_StartTakeoff();
                DjiFlightController_ObtainJoystickCtrlAuthority();
                // Dji_set_stick();
                // check_depart_ok();
            }
            else if(cmd.cmd == "COFIRMLAND"){ // directly confirm landing
                DjiFlightController_ObtainJoystickCtrlAuthority();
                DjiFlightController_StartLanding();
                DjiFlightController_StartConfirmLanding();
                DjiFlightController_ReleaseJoystickCtrlAuthority();
            }
            else if(cmd.cmd == "LAND"){ // land; if under 0.7m check fails, confirmation is required
                DjiFlightController_ObtainJoystickCtrlAuthority();
                DjiFlightController_StartLanding();
                DjiFlightController_ReleaseJoystickCtrlAuthority();
            }
            else if(cmd.cmd == "OFFCONTROL"){ // release control
                DjiFlightController_ReleaseJoystickCtrlAuthority();
            }
            else if(cmd.cmd == "HOVER"){ // hover
                DjiFlightController_ObtainJoystickCtrlAuthority();
                s_flyingCommand.x=0;s_flyingCommand.y=0;s_flyingCommand.z=0;s_flyingCommand.yaw=s_flyingCommand.yaw;
                cur_send_to_uav.v_x = 0;cur_send_to_uav.v_y = 0;cur_send_to_uav.v_z = 0; cur_send_to_uav.yaw = s_flyingCommand.yaw;
                T_DjiFlightControllerJoystickCommand stop_seq = {0};
                stop_seq.yaw = s_flyingCommand.yaw;
                // Dji_set_stick();
                DjiUser_FlightControllerVelocityAndYawRateCtrl(stop_seq);
                DjiFlightController_ObtainJoystickCtrlAuthority();
                // DjiFlightController_ReleaseJoystickCtrlAuthority();
            }
            else if(cmd.cmd == "ARM"){ // arm
                DjiFlightController_ObtainJoystickCtrlAuthority();
                DjiFlightController_TurnOnMotors();
            }
            else if(cmd.cmd == "DISARM"){ // disarm
                DjiFlightController_TurnOffMotors();
                DjiFlightController_ReleaseJoystickCtrlAuthority();
            }
            
            stopCtrlSeqCommand = false;
            USER_LOG_INFO("      [Command Listener] executed %s", cmd.cmd.c_str());
        }
        osalHandler->TaskSleepMs(1000 / CMD_FREQUENCY);
    }
    USER_LOG_INFO("      [Command Listener] ended");
    return nullptr;
}

static void * SendSeq(void* arg){
    T_DjiOsalHandler *osalHandler = DjiPlatform_GetOsalHandler();
    USER_LOG_INFO("    [Control Sequence Listener] started");
    while(!suspendCtrlSeqCommand){
        Control_seq seq = get_ctrl_seq();
        if(!seq.is_empty && cur_send_to_uav.ctrl_time != seq.ctrl_time){
            cur_send_to_uav.v_x = get_arnge_speed(seq.v_x, MAX_X_SPEED);
            cur_send_to_uav.v_y = get_arnge_speed(seq.v_y, MAX_Y_SPEED);
            cur_send_to_uav.v_z = get_arnge_speed(seq.v_z, MAX_Z_SPEED);
            cur_send_to_uav.yaw = get_arnge_speed(seq.yaw, MAX_ANGEL);
            USER_LOG_INFO("      [Control Sequence Listener] replaced with %.2f,%.2f,%.2f,%.2f", cur_send_to_uav.v_x, cur_send_to_uav.v_y, cur_send_to_uav.v_z, cur_send_to_uav.yaw);
            cur_send_to_uav.ctrl_time = seq.ctrl_time;
        }
        osalHandler->TaskSleepMs(1000 / SEQ_FREQUENCY);
    }
    USER_LOG_INFO("    [Control Sequence Listener] ended");
    return nullptr;
}

static void * ChangeSpeedSlowly(void* arg){
    T_DjiOsalHandler *osalHandler = DjiPlatform_GetOsalHandler();
    USER_LOG_INFO("    [Control Sequence Executor] started");
    while(!suspendCtrlSeqCommand){
        if(!stopCtrlSeqCommand){
            Control_seq now_speed(cur_send_to_uav);
            s_flyingCommand.x = change_speed(now_speed.v_x, speed_per_step, s_flyingCommand.x, MAX_X_SPEED);
            s_flyingCommand.y = change_speed(now_speed.v_y, speed_per_step, s_flyingCommand.y, MAX_Y_SPEED);
            s_flyingCommand.z = change_speed(now_speed.v_z, speed_per_step, s_flyingCommand.z, MAX_Z_SPEED);
            s_flyingCommand.yaw = change_speed(now_speed.yaw, angel_per_step, s_flyingCommand.yaw, MAX_ANGEL);
            USER_LOG_INFO("      [Control Sequence Executor] executing %.2f,%.2f,%.2f,%.2f", s_flyingCommand.x, s_flyingCommand.y, s_flyingCommand.z, s_flyingCommand.yaw);
        }
        osalHandler->TaskSleepMs(1000 / SEQ_CHANGE_FREQUENCY);
    }
    USER_LOG_INFO("    [Control Sequence Executor] ended");
    return nullptr;
}

static void * EmergencyReturnHome(void* arg){
    T_DjiOsalHandler *osalHandler = DjiPlatform_GetOsalHandler();
    USER_LOG_INFO("    [Emergency Detector] started");
    while(!suspendCtrlCmdCommand && !suspendCtrlSeqCommand){
        USER_LOG_INFO("      [Emergency Detector] checking");
        if(get_emergency()){
            suspendCtrlCmdCommand = true; suspendCtrlSeqCommand = true;
            USER_LOG_INFO("      [Emergency Detector] emergency detected, preparing to interrupt");
            DjiFlightController_ObtainJoystickCtrlAuthority();
            T_DjiFlightControllerJoystickCommand stop_seq = {0};
            stop_seq.yaw = s_flyingCommand.yaw;
            DjiUser_FlightControllerVelocityAndYawRateCtrl(stop_seq);
            DjiFlightController_ReleaseJoystickCtrlAuthority();
            USER_LOG_INFO("      [Emergency Detector] interrupt started, calling emergency stop");
        }
        osalHandler->TaskSleepMs(1000 / CHECK_EMERGENCY_FREQUENCY);
    }
    USER_LOG_INFO("    [Emergency Detector] ended");
    return nullptr;
}

static void * get_yaw_from_dji(void* arg){
    T_DjiOsalHandler *osalHandler = DjiPlatform_GetOsalHandler();
    USER_LOG_INFO("    [DJI Yaw Publisher] started");
    while(wait_yaw_to_publish){
        USER_LOG_INFO("      [DJI Yaw Publisher] waiting loop started");
        osalHandler->TaskSleepMs(1000);
    }
    while(!suspendCtrlCmdCommand){
        T_DjiFcSubscriptionQuaternion quaternionData;
        T_DjiDataTimestamp timestamp;
        DjiFcSubscription_GetLatestValueOfTopic(DJI_FC_SUBSCRIPTION_TOPIC_QUATERNION, 
                                                (uint8_t*)&quaternionData, 
                                                sizeof(quaternionData), 
                                                &timestamp);
        double yaw = atan2(2.0 * (quaternionData.q0 * quaternionData.q3 + quaternionData.q1 * quaternionData.q2), 1.0 - 2.0 * (quaternionData.q2 * quaternionData.q2 + quaternionData.q3 * quaternionData.q3)) /3.1415926*180;
        USER_LOG_INFO("      [DJI Yaw Publisher] current yaw -> %.2f", yaw);
        set_yaw(yaw);
        osalHandler->TaskSleepMs(1000.0 / 5.0);
    }
    USER_LOG_INFO("    [DJI Yaw Publisher] ended");
    return nullptr;
}


// Main flight-control loop
void MainFlyControlLoop(void)
{
    USER_LOG_INFO("  [Flight Control] entering main loop");
    OriginPosition original_pos = get_original_pos();
    T_DjiReturnCode returnCode;
    T_DjiOsalHandler *osalHandler = DjiPlatform_GetOsalHandler();
    
    suspendCtrlSeqCommand = false;
    suspendCtrlCmdCommand = false;

    returnCode = osalHandler->TaskCreate("command_flying_task", DjiUser_FlightControllerCommandFlyingTask,
                                         DJI_TEST_COMMAND_FLYING_TASK_STACK_SIZE, (void *) & original_pos,
                                         &s_commandFlyingTaskHandle);
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Create command flying task failed, errno = 0x%08llX", returnCode);
        return;
    }
    USER_LOG_INFO("    [Flight Control] stick-control thread started");
    // osalHandler->TaskSleepMs(3000.0);

    osalHandler->TaskCreate("command_cmd_task", ExcuteCmd,
                            DJI_TEST_COMMAND_FLYING_TASK_STACK_SIZE, nullptr,
                            &s_commandFlyingTaskHandle);
    USER_LOG_INFO("    [Flight Control] command-listener thread started");

    osalHandler->TaskCreate("command_seq_task", SendSeq,
                            DJI_TEST_COMMAND_FLYING_TASK_STACK_SIZE, nullptr,
                            &s_commandFlyingTaskHandle);
    USER_LOG_INFO("    [Flight Control] control-sequence-listener thread started");

    osalHandler->TaskCreate("excute_seq_task", ChangeSpeedSlowly,
                            DJI_TEST_COMMAND_FLYING_TASK_STACK_SIZE, nullptr,
                            &s_commandFlyingTaskHandle);
    USER_LOG_INFO("    [Flight Control] control-sequence-executor thread started");

    osalHandler->TaskCreate("excute_check_emergency_task", EmergencyReturnHome,
                            DJI_TEST_COMMAND_FLYING_TASK_STACK_SIZE, nullptr,
                            &s_commandFlyingTaskHandle);
    USER_LOG_INFO("    [Flight Control] emergency-detector thread started");
    osalHandler->TaskCreate("yaw_listen_task", get_yaw_from_dji,
                            DJI_TEST_COMMAND_FLYING_TASK_STACK_SIZE, nullptr,
                            &s_commandFlyingTaskHandle);
    USER_LOG_INFO("    [Flight Control] yaw-listener thread started");
    while(!suspendCtrlCmdCommand && !suspendCtrlSeqCommand){
        osalHandler -> TaskSleepMs(5000);
        USER_LOG_INFO("  [Flight Control Main] heartbeat..");
    }
    USER_LOG_INFO("  [Flight Control] exiting main loop");
}


/* Private functions definition-----------------------------------------------*/
static void * DjiUser_FlightControllerCommandFlyingTask(void *arg)
{
    T_DjiReturnCode returnCode;
    T_DjiOsalHandler *osalHandler = DjiPlatform_GetOsalHandler();
    T_DjiFlightControllerRidInfo ridInfo = {0};
    T_DjiFlightControllerGeneralInfo generalInfo = {0};
    OriginPosition * original_ptr = (OriginPosition *) arg;
    

    // Check whether initialization is normal
    /*Initialize the flight-controller module and set required DJI resources/config so it can run normally.
      This usually includes memory allocation, communication interface initialization, and required parameter setup. After this call, the module can perform further operations,
      such as controlling UAV flight and reading flight state data.*/
    ridInfo.latitude = 22.542812;
    ridInfo.longitude = 113.958902;
    ridInfo.altitude = 0;
    returnCode = DjiFlightController_Init(ridInfo);
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Init flight controller failed, errno = 0x%08llX", returnCode);
        return NULL;
    }
    
    /*Initialize the flight-controller data subscription module. This allows subscribing to FC data such as position, velocity, and attitude.
    The initialization allocates resources and establishes communication so follow-up subscription requests can run normally.*/
    returnCode = DjiFcSubscription_Init();
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Init data subscription module failed, error code:0x%08llX", returnCode);
        return NULL;
    }

    /* Subscribe quaternion q = w + xi + yj + zk */
    returnCode = DjiFcSubscription_SubscribeTopic(DJI_FC_SUBSCRIPTION_TOPIC_QUATERNION, DJI_DATA_SUBSCRIPTION_TOPIC_50_HZ, NULL);
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Subscribe topic flight status failed, error code:0x%08llX", returnCode);
        return NULL;
    }

    /* Subscribe GPS data */
    returnCode = DjiFcSubscription_SubscribeTopic(DJI_FC_SUBSCRIPTION_TOPIC_GPS_POSITION, DJI_DATA_SUBSCRIPTION_TOPIC_5_HZ, NULL);
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Subscribe topic gps failed, error code:0x%08llX", returnCode);
        return NULL;
    }

    /* Subscribe altitude data */
    returnCode = DjiFcSubscription_SubscribeTopic(DJI_FC_SUBSCRIPTION_TOPIC_HEIGHT_FUSION, DJI_DATA_SUBSCRIPTION_TOPIC_10_HZ, NULL);
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Subscribe topic altitude failed, error code:0x%08llX", returnCode);
        return NULL;
    }

    /* Visual odometry (INS) T_DjiFcSubscriptionPositionVO: x,y,z,yaw */
    returnCode = DjiFcSubscription_SubscribeTopic(DJI_FC_SUBSCRIPTION_TOPIC_POSITION_VO, DJI_DATA_SUBSCRIPTION_TOPIC_10_HZ, NULL);
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Subscribe topic altitude failed, error code:0x%08llX", returnCode);
        return NULL;
    }
    wait_yaw_to_publish = false;

    /* Indicates the source of the current control device (RC/mobile/third-party, etc.). */
    returnCode = DjiFcSubscription_SubscribeTopic(DJI_FC_SUBSCRIPTION_TOPIC_CONTROL_DEVICE, DJI_DATA_SUBSCRIPTION_TOPIC_5_HZ, NULL);
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Subscribe topic altitude failed, error code:0x%08llX", returnCode);
        return NULL;
    }

    osalHandler->TaskSleepMs(1000);
    /*Update flight-controller configuration. After this call,
    the FC settings can be updated based on current needs/system state, e.g. flight mode, max speed, and flight radius.
    This keeps configuration aligned with the latest control requirements for safer and more efficient flight operations.
    The return value returnCode is used to check success and determine further error handling.*/
    returnCode = DjiUser_FlightControlUpdateConfig();
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Update config failed, error code:0x%08llX", returnCode);
    }
    returnCode = DjiFlightController_GetGeneralInfo(&generalInfo);
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Get general info failed, error code:0x%08llX", returnCode);
    }
    USER_LOG_INFO("Get aircraft serial number is: %s", generalInfo.serialNum);
    returnCode = DjiFlightController_RegJoystickCtrlAuthorityEventCallback(
        DjiUser_FlightCtrlJoystickCtrlAuthSwitchEventCb);
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS && returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_NONSUPPORT) {
        USER_LOG_ERROR("Register joystick control authority event callback failed, errno = 0x%08llX", returnCode);
        return NULL;
    }
    // Dji_set_stick();
    // Flight-control loop
    static T_DjiFlightControllerJoystickCommand pre_fly_cmd = {0};
    DjiFlightController_ObtainJoystickCtrlAuthority();
    while (!suspendCtrlSeqCommand) {
        if(!stopCtrlSeqCommand){
            DjiUser_FlightControllerVelocityAndYawRateCtrl(s_flyingCommand);
            pre_fly_cmd.x = s_flyingCommand.x; pre_fly_cmd.y = s_flyingCommand.y;
            pre_fly_cmd.z = s_flyingCommand.z; pre_fly_cmd.yaw = s_flyingCommand.yaw;
            osalHandler->TaskSleepMs(1000 / DJI_TEST_COMMAND_FLYING_CTRL_FREQ);
        }
        // && !( pre_fly_cmd.x == s_flyingCommand.x && pre_fly_cmd.y == s_flyingCommand.y &&
        //     pre_fly_cmd.z == s_flyingCommand.z && pre_fly_cmd.yaw == s_flyingCommand.yaw)
    }
    USER_LOG_INFO("    [Flight Control] stick-control thread exited");
    return nullptr;
}


static void DjiUser_FlightControllerVelocityAndYawRateCtrl(T_DjiFlightControllerJoystickCommand command)
{
    // T_DjiFlightControllerJoystickMode joystickMode = {
    //     DJI_FLIGHT_CONTROLLER_HORIZONTAL_VELOCITY_CONTROL_MODE, // Control mode for horizontal velocity (±30m/s)
    //     DJI_FLIGHT_CONTROLLER_VERTICAL_VELOCITY_CONTROL_MODE, // Control mode for vertical velocity (±5m/s)
    //     DJI_FLIGHT_CONTROLLER_YAW_ANGLE_CONTROL_MODE, // Yaw angle uses ground coordinate frame. In this mode, auto-flight is forced to use ground frame.
    //     DJI_FLIGHT_CONTROLLER_HORIZONTAL_GROUND_COORDINATE, // Ground coordinate frame
    //     DJI_FLIGHT_CONTROLLER_STABLE_CONTROL_MODE_ENABLE, // Stable control mode
    // };
    
    // DjiFlightController_SetJoystickMode(joystickMode);

    // USER_LOG_INFO("DjiFlightController_SetJoystickMode, successfully!");
    
    Dji_set_stick();
    T_DjiReturnCode returnCode;
    
    returnCode = DjiFlightController_ExecuteJoystickAction(command);
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("        [DJI Joystick Executor failed]Execute joystick command failed, errno = 0x%08llX", returnCode);
        DjiFlightController_ObtainJoystickCtrlAuthority();
        return;
    }
    USER_LOG_DEBUG("        [DJI Joystick Executor success] %.2f %.2f %.2f %.2f", command.x, command.y, command.z, command.yaw);
}


static T_DjiReturnCode
DjiUser_FlightCtrlJoystickCtrlAuthSwitchEventCb(T_DjiFlightControllerJoystickCtrlAuthorityEventInfo eventData)
{
    switch (eventData.joystickCtrlAuthoritySwitchEvent) {
        case DJI_FLIGHT_CONTROLLER_MSDK_GET_JOYSTICK_CTRL_AUTH_EVENT: {
            if (eventData.curJoystickCtrlAuthority == DJI_FLIGHT_CONTROLLER_JOYSTICK_CTRL_AUTHORITY_MSDK) {
                USER_LOG_INFO("[Event] Msdk request to obtain joystick ctrl authority\r\n");
            } else {
                USER_LOG_INFO("[Event] Msdk request to release joystick ctrl authority\r\n");
            }
            break;
        }
        case DJI_FLIGHT_CONTROLLER_INTERNAL_GET_JOYSTICK_CTRL_AUTH_EVENT: {
            if (eventData.curJoystickCtrlAuthority == DJI_FLIGHT_CONTROLLER_JOYSTICK_CTRL_AUTHORITY_INTERNAL) {
                USER_LOG_INFO("[Event] Internal request to obtain joystick ctrl authority\r\n");
            } else {
                USER_LOG_INFO("[Event] Internal request to release joystick ctrl authority\r\n");
            }
            break;
        }
        case DJI_FLIGHT_CONTROLLER_OSDK_GET_JOYSTICK_CTRL_AUTH_EVENT: {
            if (eventData.curJoystickCtrlAuthority == DJI_FLIGHT_CONTROLLER_JOYSTICK_CTRL_AUTHORITY_OSDK) {
                USER_LOG_INFO("[Event] Request to obtain joystick ctrl authority\r\n");
            } else {
                USER_LOG_INFO("[Event] Request to release joystick ctrl authority\r\n");
            }
            break;
        }
        case DJI_FLIGHT_CONTROLLER_RC_LOST_GET_JOYSTICK_CTRL_AUTH_EVENT :
            USER_LOG_INFO("[Event] Current joystick ctrl authority is reset to rc due to rc lost\r\n");
            break;
        case DJI_FLIGHT_CONTROLLER_RC_NOT_P_MODE_RESET_JOYSTICK_CTRL_AUTH_EVENT :
            USER_LOG_INFO("[Event] Current joystick ctrl authority is reset to rc for rc is not in P mode\r\n");
            break;
        case DJI_FLIGHT_CONTROLLER_RC_SWITCH_MODE_GET_JOYSTICK_CTRL_AUTH_EVENT :
            USER_LOG_INFO("[Event] Current joystick ctrl authority is reset to rc due to rc switching mode\r\n");
            break;
        case DJI_FLIGHT_CONTROLLER_RC_PAUSE_GET_JOYSTICK_CTRL_AUTH_EVENT :
            USER_LOG_INFO("[Event] Current joystick ctrl authority is reset to rc due to rc pausing\r\n");
            break;
        case DJI_FLIGHT_CONTROLLER_RC_REQUEST_GO_HOME_GET_JOYSTICK_CTRL_AUTH_EVENT :
            USER_LOG_INFO("[Event] Current joystick ctrl authority is reset to rc due to rc request for return\r\n");
            break;
        case DJI_FLIGHT_CONTROLLER_LOW_BATTERY_GO_HOME_RESET_JOYSTICK_CTRL_AUTH_EVENT :
            USER_LOG_INFO("[Event] Current joystick ctrl authority is reset to rc for low battery return\r\n");
            break;
        case DJI_FLIGHT_CONTROLLER_LOW_BATTERY_LANDING_RESET_JOYSTICK_CTRL_AUTH_EVENT :
            USER_LOG_INFO("[Event] Current joystick ctrl authority is reset to rc for low battery land\r\n");
            break;
        case DJI_FLIGHT_CONTROLLER_OSDK_LOST_GET_JOYSTICK_CTRL_AUTH_EVENT:
            USER_LOG_INFO("[Event] Current joystick ctrl authority is reset to rc due to sdk lost\r\n");
            break;
        case DJI_FLIGHT_CONTROLLER_NERA_FLIGHT_BOUNDARY_RESET_JOYSTICK_CTRL_AUTH_EVENT :
            USER_LOG_INFO("[Event] Current joystick ctrl authority is reset to rc due to near boundary\r\n");
            break;
        default:
            USER_LOG_INFO("[Event] Unknown joystick ctrl authority event\r\n");
    }

    return DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS;
}


static T_DjiFcSubscriptionGpsPosition DjiUser_FlightControlGetValueOfGpsPosition(void)
{
    T_DjiReturnCode djiStat;
    T_DjiDataTimestamp timestamp = {0};
    T_DjiFcSubscriptionGpsPosition gpsPosition;

    djiStat = DjiFcSubscription_GetLatestValueOfTopic(DJI_FC_SUBSCRIPTION_TOPIC_GPS_POSITION,
                                                      (uint8_t *) &gpsPosition,
                                                      sizeof(T_DjiFcSubscriptionGpsPosition),
                                                      &timestamp);

    if (djiStat != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Get value of topic quaternion error, error code: 0x%08X", djiStat);
    } else {
        USER_LOG_DEBUG("Timestamp: millisecond %u microsecond %u.", timestamp.millisecond,
                       timestamp.microsecond);
    }

    return gpsPosition;
}

static T_DjiFcSubscriptionAltitudeOfHomePoint DjiUser_FlightControlGetValueOfRelativeHeight(void)
{
    T_DjiReturnCode djiStat;
    T_DjiDataTimestamp timestamp = {0};
    T_DjiFcSubscriptionAltitudeOfHomePoint altitudeOfHomePoint;

    djiStat = DjiFcSubscription_GetLatestValueOfTopic(DJI_FC_SUBSCRIPTION_TOPIC_HEIGHT_FUSION,
                                                      (uint8_t *) &altitudeOfHomePoint,
                                                      sizeof(T_DjiFcSubscriptionAltitudeOfHomePoint),
                                                      &timestamp);

    if (djiStat != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Get value of topic quaternion error, error code: 0x%08X", djiStat);
    } else {
        USER_LOG_DEBUG("Timestamp: millisecond %u microsecond %u.", timestamp.millisecond,
                       timestamp.microsecond);
    }

    return altitudeOfHomePoint;
}

static T_DjiFcSubscriptionPositionVO DjiUser_FlightControlGetValueOfPositionVo(void)
{
    T_DjiReturnCode djiStat;
    T_DjiDataTimestamp timestamp = {0};
    T_DjiFcSubscriptionPositionVO positionVo;

    djiStat = DjiFcSubscription_GetLatestValueOfTopic(DJI_FC_SUBSCRIPTION_TOPIC_POSITION_VO,
                                                      (uint8_t *) &positionVo,
                                                      sizeof(T_DjiFcSubscriptionPositionVO),
                                                      &timestamp);

    if (djiStat != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Get value of topic quaternion error, error code: 0x%08X", djiStat);
    } else {
        USER_LOG_DEBUG("Timestamp: millisecond %u microsecond %u.", timestamp.millisecond,
                       timestamp.microsecond);
    }

    return positionVo;
}

static T_DjiReturnCode DjiUser_FlightControlUpdateConfig(void)
{
    T_DjiReturnCode returnCode;
    char curFileDirPath[DJI_TEST_COMMAND_FLYING_CONFIG_DIR_PATH_LEN_MAX];
    char tempFileDirPath[DJI_TEST_COMMAND_FLYING_CONFIG_DIR_PATH_LEN_MAX];
    uint32_t fileSize = 0;
    uint32_t readRealSize = 0;
    T_DjiOsalHandler *osalHandler = DjiPlatform_GetOsalHandler();
    uint8_t *jsonData = nullptr;
    cJSON *jsonRoot = nullptr;
    cJSON *jsonItem = nullptr;
    cJSON *jsonValue = nullptr;
    T_DjiAircraftInfoBaseInfo aircraftInfoBaseInfo;

    returnCode = DjiAircraftInfo_GetBaseInfo(&aircraftInfoBaseInfo);
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("get aircraft base info error");
    }

#ifdef SYSTEM_ARCH_LINUX
    returnCode = DjiUserUtil_GetCurrentFileDirPath(__FILE__, DJI_TEST_COMMAND_FLYING_CONFIG_DIR_PATH_LEN_MAX,
                                                   curFileDirPath);
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Get file current path error, stat = 0x%08llX", returnCode);
        return returnCode;
    }

    snprintf(tempFileDirPath, DJI_TEST_COMMAND_FLYING_CONFIG_DIR_PATH_LEN_MAX, "%s/config/flying_config.json",
             curFileDirPath);

    returnCode = UtilFile_GetFileSizeByPath(tempFileDirPath, &fileSize);
    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
        USER_LOG_ERROR("Get file size by path failed, stat = 0x%08llX", returnCode);
        return returnCode;
    }

    USER_LOG_DEBUG("Get config json file size is %d", fileSize);

    jsonData = static_cast<uint8_t *>(osalHandler->Malloc(fileSize + 1));
    if (jsonData == nullptr) {
        USER_LOG_ERROR("Malloc failed.");
        return DJI_ERROR_SYSTEM_MODULE_CODE_SYSTEM_ERROR;
    }

    memset(jsonData, 0, fileSize);

    UtilFile_GetFileDataByPath(tempFileDirPath, 0, fileSize, jsonData, &readRealSize);

    jsonData[readRealSize] = '\0';

    jsonRoot = cJSON_Parse((char *) jsonData);
    if (jsonRoot == nullptr) {
        return DJI_ERROR_SYSTEM_MODULE_CODE_UNKNOWN;
    }

    jsonItem = cJSON_GetObjectItem(jsonRoot, "go_home_altitude");
    if (jsonItem != nullptr) {
        jsonValue = cJSON_GetObjectItem(jsonItem, "value");
        if (jsonValue != nullptr) {
            USER_LOG_INFO("Get go home altitude is [%.2f]", jsonValue->valuedouble);
            s_goHomeAltitude = (uint16_t) jsonValue->valuedouble;
            returnCode = DjiFlightController_SetGoHomeAltitude((uint16_t) jsonValue->valuedouble);
            if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                USER_LOG_ERROR("Set go home altitude failed, errno = 0x%08llX", returnCode);
                return returnCode;
            }
        }
    }

    if (aircraftInfoBaseInfo.aircraftSeries != DJI_AIRCRAFT_SERIES_M300) {
        jsonItem = cJSON_GetObjectItem(jsonRoot, "rc_lost_action");
        if (jsonItem != nullptr) {
            jsonValue = cJSON_GetObjectItem(jsonItem, "value");
            if (jsonValue != nullptr) {
                USER_LOG_INFO("Get rc lost action is [%s]", jsonValue->valuestring);
                strcpy(s_rcLostActionString, jsonValue->valuestring);
                if (strcmp(jsonValue->valuestring, "go_home") == 0) {
                    returnCode = DjiFlightController_SetRCLostAction(DJI_FLIGHT_CONTROLLER_RC_LOST_ACTION_GOHOME);
                    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                        USER_LOG_ERROR("Set rc lost action failed, errno = 0x%08llX", returnCode);
                        return returnCode;
                    }
                } else if (strcmp(jsonValue->valuestring, "hover") == 0) {
                    returnCode = DjiFlightController_SetRCLostAction(DJI_FLIGHT_CONTROLLER_RC_LOST_ACTION_HOVER);
                    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                        USER_LOG_ERROR("Set rc lost action failed, errno = 0x%08llX", returnCode);
                        return returnCode;
                    }
                } else if (strcmp(jsonValue->valuestring, "landing") == 0) {
                    returnCode = DjiFlightController_SetRCLostAction(DJI_FLIGHT_CONTROLLER_RC_LOST_ACTION_LANDING);
                    if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                        USER_LOG_ERROR("Set rc lost action failed, errno = 0x%08llX", returnCode);
                        return returnCode;
                    }
                } else {
                    USER_LOG_ERROR("Invalid value: %s", jsonValue->valuestring);
                }
            }
        }
    }

    jsonItem = cJSON_GetObjectItem(jsonRoot, "flying_speed");
    if (jsonItem != nullptr) {
        jsonValue = cJSON_GetObjectItem(jsonItem, "value");
        if (jsonValue != nullptr) {
            USER_LOG_INFO("Get flying speed is [%.2f]", jsonValue->valuedouble);
            s_flyingSpeed = jsonValue->valuedouble;
        }
    }

    jsonItem = cJSON_GetObjectItem(jsonRoot, "rtk_enable");
    if (jsonItem != nullptr) {
        jsonValue = cJSON_GetObjectItem(jsonItem, "value");
        if (jsonValue != nullptr) {
            USER_LOG_INFO("Get rtk enable is [%s]", jsonValue->valuestring);
            if (strcmp(jsonValue->valuestring, "true") == 0) {
                returnCode = DjiFlightController_SetRtkPositionEnableStatus(DJI_FLIGHT_CONTROLLER_ENABLE_RTK_POSITION);
                if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                    USER_LOG_ERROR("Set rtk enable failed, errno = 0x%08llX", returnCode);
                    return returnCode;
                }
            } else if (strcmp(jsonValue->valuestring, "false") == 0) {
                returnCode = DjiFlightController_SetRtkPositionEnableStatus(DJI_FLIGHT_CONTROLLER_DISABLE_RTK_POSITION);
                if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                    USER_LOG_ERROR("Set rtk enable failed, errno = 0x%08llX", returnCode);
                    return returnCode;
                }
            } else {
                USER_LOG_ERROR("Invalid value: %s", jsonValue->valuestring);
            }
        }
    }

    jsonItem = cJSON_GetObjectItem(jsonRoot, "home_point_latitude");
    if (jsonItem != nullptr) {
        jsonValue = cJSON_GetObjectItem(jsonItem, "value");
        if (jsonValue != nullptr) {
            USER_LOG_INFO("Get home_point_latitude  is [%.2f]", jsonValue->valuedouble);
            s_homeLocation.latitude = jsonValue->valuedouble;
        }
    }
    jsonItem = cJSON_GetObjectItem(jsonRoot, "home_point_longitude");
    if (jsonItem != nullptr) {
        jsonValue = cJSON_GetObjectItem(jsonItem, "value");
        if (jsonValue != nullptr) {
            USER_LOG_INFO("Get home_point_longitude is [%.2f]", jsonValue->valuedouble);
            s_homeLocation.longitude = jsonValue->valuedouble;
        }
    }

    if (isFirstUpdateConfig == false) {
        USER_LOG_INFO("Using current aircraft location, not use config home location.");
        s_gpsPosition = DjiUser_FlightControlGetValueOfGpsPosition();
        s_homeLocation.latitude = (dji_f64_t) s_gpsPosition.y / 10000000;
        s_homeLocation.longitude = (dji_f64_t) s_gpsPosition.x / 10000000;

        returnCode = DjiFlightController_SetHomeLocationUsingCurrentAircraftLocation();
        if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
            USER_LOG_ERROR("Set home location failed, errno = 0x%08llX", returnCode);
        }
        isFirstUpdateConfig = true;
    } else {
        T_DjiFlightControllerHomeLocation homeLocation;
        homeLocation.latitude = s_homeLocation.latitude * DJI_PI / 180;
        homeLocation.longitude = s_homeLocation.longitude * DJI_PI / 180;

        returnCode = DjiFlightController_SetHomeLocationUsingGPSCoordinates(homeLocation);
        if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
            USER_LOG_ERROR("Set home location failed, errno = 0x%08llX", returnCode);
            return returnCode;
        }
    }

    jsonItem = cJSON_GetObjectItem(jsonRoot, "HorizontalVisualObstacleAvoidanceEnable");
    if (jsonItem != nullptr) {
        jsonValue = cJSON_GetObjectItem(jsonItem, "value");
        if (jsonValue != nullptr) {
            USER_LOG_INFO("Get HorizontalVisualObstacleAvoidanceEnable is [%s]", jsonValue->valuestring);
            if (strcmp(jsonValue->valuestring, "true") == 0) {
                returnCode = DjiFlightController_SetHorizontalVisualObstacleAvoidanceEnableStatus(
                    DJI_FLIGHT_CONTROLLER_ENABLE_OBSTACLE_AVOIDANCE);
                if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                    USER_LOG_ERROR("Set HorizontalVisualObstacleAvoidanceEnable failed, errno = 0x%08llX", returnCode);
                    return returnCode;
                }
            } else if (strcmp(jsonValue->valuestring, "false") == 0) {
                returnCode = DjiFlightController_SetHorizontalVisualObstacleAvoidanceEnableStatus(
                    DJI_FLIGHT_CONTROLLER_DISABLE_OBSTACLE_AVOIDANCE);
                if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                    USER_LOG_ERROR("Set HorizontalVisualObstacleAvoidanceEnable failed, errno = 0x%08llX", returnCode);
                    return returnCode;
                }
            } else {
                USER_LOG_ERROR("Invalid value: %s", jsonValue->valuestring);
            }
        }
    }

   jsonItem = cJSON_GetObjectItem(jsonRoot, "HorizontalRadarObstacleAvoidanceEnable");
   if (jsonItem != nullptr) {
       if (aircraftInfoBaseInfo.aircraftType == DJI_AIRCRAFT_TYPE_M300_RTK ||
           aircraftInfoBaseInfo.aircraftType == DJI_AIRCRAFT_TYPE_M30 ||
           aircraftInfoBaseInfo.aircraftType == DJI_AIRCRAFT_TYPE_M30T ||
           aircraftInfoBaseInfo.aircraftType == DJI_AIRCRAFT_TYPE_M350_RTK) {
           jsonValue = cJSON_GetObjectItem(jsonItem, "value");
           if (jsonValue != nullptr) {
               USER_LOG_INFO("Get HorizontalRadarObstacleAvoidanceEnable is [%s]", jsonValue->valuestring);
               if (strcmp(jsonValue->valuestring, "true") == 0) {
                   returnCode = DjiFlightController_SetHorizontalRadarObstacleAvoidanceEnableStatus(
                       DJI_FLIGHT_CONTROLLER_ENABLE_OBSTACLE_AVOIDANCE);
                   if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                       USER_LOG_ERROR("Set HorizontalRadarObstacleAvoidanceEnable failed, errno = 0x%08llX",
                                      returnCode);
                       return returnCode;
                   }
               } else if (strcmp(jsonValue->valuestring, "false") == 0) {
                   returnCode = DjiFlightController_SetHorizontalRadarObstacleAvoidanceEnableStatus(
                       DJI_FLIGHT_CONTROLLER_DISABLE_OBSTACLE_AVOIDANCE);
                   if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                       USER_LOG_ERROR("Set HorizontalRadarObstacleAvoidanceEnable failed, errno = 0x%08llX",
                                      returnCode);
                       return returnCode;
                   }
               } else {
                   USER_LOG_ERROR("Invalid value: %s", jsonValue->valuestring);
               }
           }
       }
   }

    jsonItem = cJSON_GetObjectItem(jsonRoot, "UpwardsVisualObstacleAvoidanceEnable");
    if (jsonItem != nullptr) {
        jsonValue = cJSON_GetObjectItem(jsonItem, "value");
        if (jsonValue != nullptr) {
            USER_LOG_INFO("Get UpwardsVisualObstacleAvoidanceEnable is [%s]", jsonValue->valuestring);
            if (strcmp(jsonValue->valuestring, "true") == 0) {
                returnCode = DjiFlightController_SetUpwardsVisualObstacleAvoidanceEnableStatus(
                    DJI_FLIGHT_CONTROLLER_ENABLE_OBSTACLE_AVOIDANCE);
                if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                    USER_LOG_ERROR("Set UpwardsVisualObstacleAvoidanceEnable failed, errno = 0x%08llX", returnCode);
                    return returnCode;
                }
            } else if (strcmp(jsonValue->valuestring, "false") == 0) {
                returnCode = DjiFlightController_SetUpwardsVisualObstacleAvoidanceEnableStatus(
                    DJI_FLIGHT_CONTROLLER_DISABLE_OBSTACLE_AVOIDANCE);
                if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                    USER_LOG_ERROR("Set UpwardsVisualObstacleAvoidanceEnable failed, errno = 0x%08llX", returnCode);
                    return returnCode;
                }
            } else {
                USER_LOG_ERROR("Invalid value: %s", jsonValue->valuestring);
            }
        }
    }

   jsonItem = cJSON_GetObjectItem(jsonRoot, "UpwardsRadarObstacleAvoidanceEnable");
   if (jsonItem != nullptr) {
       if (aircraftInfoBaseInfo.aircraftType == DJI_AIRCRAFT_TYPE_M300_RTK ||
           aircraftInfoBaseInfo.aircraftType == DJI_AIRCRAFT_TYPE_M30 ||
           aircraftInfoBaseInfo.aircraftType == DJI_AIRCRAFT_TYPE_M30T ||
           aircraftInfoBaseInfo.aircraftType == DJI_AIRCRAFT_TYPE_M350_RTK) {
           jsonValue = cJSON_GetObjectItem(jsonItem, "value");
           if (jsonValue != nullptr) {
               USER_LOG_INFO("Get UpwardsRadarObstacleAvoidanceEnable is [%s]", jsonValue->valuestring);
               if (strcmp(jsonValue->valuestring, "true") == 0) {
                   returnCode = DjiFlightController_SetUpwardsRadarObstacleAvoidanceEnableStatus(
                       DJI_FLIGHT_CONTROLLER_ENABLE_OBSTACLE_AVOIDANCE);
                   if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                       USER_LOG_ERROR("Set UpwardsRadarObstacleAvoidanceEnable failed, errno = 0x%08llX", returnCode);
                       return returnCode;
                   }
               } else if (strcmp(jsonValue->valuestring, "false") == 0) {
                   returnCode = DjiFlightController_SetUpwardsRadarObstacleAvoidanceEnableStatus(
                       DJI_FLIGHT_CONTROLLER_DISABLE_OBSTACLE_AVOIDANCE);
                   if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                       USER_LOG_ERROR("Set UpwardsRadarObstacleAvoidanceEnable failed, errno = 0x%08llX", returnCode);
                       return returnCode;
                   }
               } else {
                   USER_LOG_ERROR("Invalid value: %s", jsonValue->valuestring);
               }
           }
       }
   }

    jsonItem = cJSON_GetObjectItem(jsonRoot, "DownwardsVisualObstacleAvoidanceEnable");
    if (jsonItem != nullptr) {
        jsonValue = cJSON_GetObjectItem(jsonItem, "value");
        if (jsonValue != nullptr) {
            USER_LOG_INFO("Get DownwardsVisualObstacleAvoidanceEnable is [%s]", jsonValue->valuestring);
            if (strcmp(jsonValue->valuestring, "true") == 0) {
                returnCode = DjiFlightController_SetDownwardsVisualObstacleAvoidanceEnableStatus(
                    DJI_FLIGHT_CONTROLLER_ENABLE_OBSTACLE_AVOIDANCE);
                if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                    USER_LOG_ERROR("Set DownwardsVisualObstacleAvoidanceEnable failed, errno = 0x%08llX", returnCode);
                    return returnCode;
                }
            } else if (strcmp(jsonValue->valuestring, "false") == 0) {
                returnCode = DjiFlightController_SetDownwardsVisualObstacleAvoidanceEnableStatus(
                    DJI_FLIGHT_CONTROLLER_DISABLE_OBSTACLE_AVOIDANCE);
                if (returnCode != DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS) {
                    USER_LOG_ERROR("Set DownwardsVisualObstacleAvoidanceEnable failed, errno = 0x%08llX", returnCode);
                    return returnCode;
                }
            } else {
                USER_LOG_ERROR("Invalid value: %s", jsonValue->valuestring);
            }
        }
    }

    osalHandler->Free(jsonData);

    return DJI_ERROR_SYSTEM_MODULE_CODE_SUCCESS;
#endif
}

/****************** (C) COPYRIGHT DJI Innovations *****END OF FILE****/
