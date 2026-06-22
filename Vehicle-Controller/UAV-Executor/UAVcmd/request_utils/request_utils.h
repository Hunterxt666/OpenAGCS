#ifndef REQUEST_UTILS_H
#define REQUEST_UTILS_H

#define REMOTE_IP_ADRESS "REMOTE_IP_ADDRESS" // Replace with actual remote IP address
#define LOCAL_IP_ADRESS "http://127.0.0.1:26969"

#include <string>

struct Control_seq {
    double v_x, v_y, v_z, yaw, ctrl_time;
    bool is_empty;
    Control_seq(double v_x, double v_y, double v_z, double yaw, double ctrl_time);
    Control_seq();
    Control_seq(const Control_seq& other);
};

struct Control_cmd {
    std::string cmd;
    double ctrl_time;
    bool is_empty;
    Control_cmd(double ctrl_time, const std::string& cmd);
    Control_cmd();
};

struct OriginPosition {
    double longitude, latitude;
    bool is_empty;
    OriginPosition(double longitude, double latitude);
    OriginPosition();
};

std::string get(const std::string&, const std::string&);
OriginPosition get_original_pos(void);
Control_seq get_ctrl_seq(void);
Control_cmd get_ctrl_cmd(void);
bool get_emergency(void);
void set_yaw(double);

#endif // REQUEST_UTILS_H