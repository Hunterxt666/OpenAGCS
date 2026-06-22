// request_utils.cpp

#include "request_utils.h"
#include <curl/curl.h>
#include <iostream>
#include "json.hpp" 
#include <string>
#include <unistd.h>
#include "dji_logger.h"
#include <sstream>
#include <iomanip>
#include <chrono>
#include <ctime>

using json = nlohmann::json;

using namespace std;

Control_seq::Control_seq(double v_x, double v_y, double v_z, double yaw, double ctrl_time)
    : v_x(v_x), v_y(v_y), v_z(v_z), yaw(yaw), ctrl_time(ctrl_time), is_empty(false) {}

Control_seq::Control_seq() : is_empty(true) {}

Control_seq::Control_seq(const Control_seq& other) : ctrl_time(0), is_empty(false) {
    v_x = other.v_x;
    v_y = other.v_y; 
    v_z = other.v_z; 
    yaw = other.yaw; 
    ctrl_time = other.ctrl_time;
}

Control_cmd::Control_cmd(double ctrl_time, const string& cmd) : ctrl_time(ctrl_time), cmd(cmd), is_empty(false) {}

Control_cmd::Control_cmd() : is_empty(true) {}

OriginPosition::OriginPosition(double longitude, double latitude) : longitude(longitude), latitude(latitude), is_empty(true) {}

OriginPosition::OriginPosition() : is_empty(true) {}

string getFormattedTime() {
    // Get current time
    auto now = chrono::system_clock::now();
    auto now_time_t = chrono::system_clock::to_time_t(now);
    auto now_microseconds = chrono::duration_cast<chrono::microseconds>(now.time_since_epoch()) % 1000000;

    // Convert to local time
    tm *time_info = localtime(&now_time_t);

    // Format with stringstream
    stringstream ss;
    ss << put_time(time_info, "%Y%m%d%H%M%S") 
       << setw(6) << setfill('0') << now_microseconds.count();

    return ss.str();
}

// CURL callback to write received data
size_t WriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    ((string *)userp)->append((char*)contents, size * nmemb);
    return size * nmemb;
}

// Perform GET request for a URL
string get(const string & address, const string& type = string("Local")) {
    CURL* curl;
    CURLcode res;
    string response;
    long http_code;

    curl = curl_easy_init();
    string url = type == "Remote"?REMOTE_IP_ADRESS:LOCAL_IP_ADRESS;
    url += address;
    if (curl) {
        // Set URL
        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());

        // Set callback to receive response
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
        if (type == "Local"){
            curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT_MS, 250L);  // Connection timeout (ms)
            curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, 250L);  // Request timeout (ms)
        }
        else{
            curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT_MS, 500L);  // Connection timeout (ms)
            curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, 500L);  // Request timeout (ms)
        }
        // Execute request
        res = curl_easy_perform(curl);

        // Check whether request succeeded
        if (res != CURLE_OK) {
            USER_LOG_INFO("         [Request] %s timed out", url.c_str());
            return "";
        }
        else{
            curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
            if(http_code != 200){
                curl_easy_cleanup(curl);
                USER_LOG_INFO("         [Request] %s returned non-200", url.c_str());
                // cout << "http request failed" << endl;
                return "";
            }
        }
        // Release CURL resources
        curl_easy_cleanup(curl);
    } else {
        return "";
    }
    USER_LOG_INFO("         [Request] %s succeeded", url.c_str());
    return response;
}

bool get_emergency(void){
    string original_re = get(string("/emergencyStop"), string("Remote"));
    if(!original_re.empty()){    
        json re_json = json::parse(original_re);
        // cout << re_json << endl;
        USER_LOG_INFO("         [Request] get_emergency succeeded");
        return re_json.at("emergency_stop_flag").get<bool>();
    }
    else{
        USER_LOG_INFO("         [Request] get_emergency failed");
        return false;
    }
}

OriginPosition get_original_pos(void){
    string original_re = "";
    while (original_re.empty()){
        original_re = get(string("/originPos"));
        USER_LOG_INFO("         [Request] get_original_pos in progress..");
        sleep(2);
    }

    json re_json = json::parse(original_re);
    USER_LOG_INFO("         [Request] get_original_pos succeeded");
    // Access JSON fields
    return OriginPosition(re_json["longitude"],re_json["latitude"]);
} 

Control_seq get_ctrl_seq(void){
    string original_re = get(string("/uavControl"));
    if(!original_re.empty()){    
        json re_json = json::parse(original_re);
        // cout << re_json << endl;
        USER_LOG_INFO("         [Request] get_ctrl_seq succeeded");
        return Control_seq(re_json["v_x"], re_json["v_y"], re_json["v_z"], re_json["yaw"], re_json["time"]);
    }
    else{
        USER_LOG_INFO("         [Request] get_ctrl_seq failed");
        return Control_seq();
    }
}

Control_cmd get_ctrl_cmd(void){
    string original_re = get(string("/uavControlCmd"));
    if(!original_re.empty()){    
        json re_json = json::parse(original_re);
        USER_LOG_INFO("         [Request] get_ctrl_cmd succeeded");
        return Control_cmd(re_json["time"], re_json.at("cmd").get<string>());
    }
    else{
        USER_LOG_INFO("         [Request] get_ctrl_cmd failed");
        return Control_cmd();
    }
}

void set_yaw(double yaw){
    string original_re = get(string("/setOrientation?orientation=") + to_string(yaw) + string("&time=") + getFormattedTime() + string("&agent=UAV"));
    if(!original_re.empty()){    
        USER_LOG_INFO("         [Request] set_yaw succeeded");
    }
    else{
        USER_LOG_INFO("         [Request] set_yaw failed");
    }
}
