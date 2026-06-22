"""UAV follow-control agent used in the paper's onboard computation pipeline."""

import math
from Tools.RequestTools import get_pos, get_pos_remote, get_height, set_uav_control_input, set_uav_control_input_cmd, check_depart
import Tools.LogUtil as log
import threading
import time


class DroneAgent:
    def __init__(self, url_local, url_remote, max_xy_speed=10, max_angel=180, max_z_speed=5):
        """
        Maintain UAV/UGV state and generate velocity commands for follow control.
        """
        self.max_angel = max_angel  # Maximum angle (deg)
        self.max_xy_speed = max_xy_speed  # Maximum horizontal speed (m/s)
        self.max_z_speed = max_z_speed   # Maximum vertical speed (m/s)
        self.url_local = url_local  # Local URL
        self.url_remote = url_remote  # Remote URL
        """
        Basic data: position and timestamp
        """
        # UAV
        self.pos = [None] * 3
        self.pre_pos = [None] * 3
        self.yaw = 0
        self.t = 0
        self.pre_t = -1
        self.vx = 0
        self.vy = 0
        # UGV
        self.ugv_pos = [None] * 2
        self.ugv_pre_pos = [None] * 2
        self.ugv_yaw = 0
        self.ugv_t = 0
        self.ugv_pre_t = -1
        self.ugv_vx = 0
        self.ugv_vy = 0
        """
        Control sub-command set
        """
        self.cmd = ["TAKEOFF", "COFIRMLAND", "LAND", "OFFCONTROL", "HOVER"]
        """
        Method for sending speed control
        """
        self.ctrl_seq = [0] * 4
        self.send_speed_thread = threading.Thread(target=self.set_uav_control_to_local)  # Thread for sending sequence
        self.send_speed_thread.start()
        """
        Position collection thread
        """
        self.send_uav_get_pos_from_local_thread = threading.Thread(target=self.uav_get_pos_from_local)
        self.send_uav_get_pos_from_local_thread.start()
        self.send_get_ugv_pos_from_remote_thread = threading.Thread(target=self.get_ugv_pos_from_remote)
        self.send_get_ugv_pos_from_remote_thread.start()
        self.send_uav_get_height_from_local_thread = threading.Thread(target=self.uav_get_height_from_local)
        self.send_uav_get_height_from_local_thread.start()
        self.check_order_thread = threading.Thread(target=self.check_depart_status)
        self.check_order_thread.start()
        """
        Follow task flag
        """
        self.depart_flag = True
        self.departed = True
        self.stop_flag = False
        self.ctrl_process = None
        self.remote_depart_order = False

    """
    Position collection thread function (continuous)
    """
    def uav_get_pos_from_local(self):
        while True:
            pos_data = get_pos(self.url_local)  # [json["current_pos"], json["time"]]
            if pos_data:
                self.pos[0] = pos_data["current_pos"][0]
                self.pos[1] = pos_data["current_pos"][1]
                self.t = pos_data["time"]
                if self.pre_pos[0] is not None and self.t-self.pre_t != 0:
                    self.yaw = math.atan2(self.pos[0] - self.pre_pos[0], self.pos[1] - self.pre_pos[1])
                    self.vx = (self.pos[0] - self.pre_pos[0])/(self.t - self.pre_t)
                    self.vy = (self.pos[1] - self.pre_pos[1])/(self.t - self.pre_t)
                self.pre_pos[0] = pos_data["current_pos"][0]
                self.pre_pos[1] = pos_data["current_pos"][1]
                self.pre_t = pos_data["time"]
            time.sleep(0.1)

    def uav_get_height_from_local(self):
        while True:
            uav_height_data = get_height(self.url_local)
            if uav_height_data:
                self.pre_pos[2] = self.pos[2]
                self.pos[2] = uav_height_data
            time.sleep(0.1)

    def check_depart_status(self):
        while True:
            self.remote_depart_order = check_depart(self.url_remote)
            time.sleep(5)

    def get_ugv_pos_from_remote(self):
        while True:
            ugv_pos_data = get_pos_remote(self.url_remote)  # [json["current_pos"], json["time"]]
            if ugv_pos_data:
                self.ugv_pos[0] = ugv_pos_data["current_pos"][0]
                self.ugv_pos[1] = ugv_pos_data["current_pos"][1]
                self.ugv_t = ugv_pos_data["time"]
                if self.ugv_pre_pos[0] is not None and self.ugv_t - self.ugv_pre_t != 0:
                    self.ugv_yaw = math.atan2(self.ugv_pos[0] - self.ugv_pre_pos[0], self.ugv_pos[1] - self.ugv_pre_pos[1])
                    self.ugv_vx = (self.ugv_pos[0] - self.ugv_pre_pos[0]) / (self.ugv_t - self.ugv_pre_t)
                    self.ugv_vy = (self.ugv_pos[1] - self.ugv_pre_pos[1]) / (self.ugv_t - self.ugv_pre_t)
                self.ugv_pre_pos[0] = ugv_pos_data["current_pos"][0]
                self.ugv_pre_pos[1] = ugv_pos_data["current_pos"][1]
                self.ugv_pre_t = ugv_pos_data["time"]
            time.sleep(0.1)

    def set_uav_control_to_local(self):
        while True:
            if self.departed:
                set_uav_control_input(
                    url=self.url_local, vx=self.ctrl_seq[0], vy=self.ctrl_seq[1], vz=self.ctrl_seq[2], yaw=self.ctrl_seq[3]
                )
            time.sleep(1 / 5)

    def set_uav_control_cmd_to_local(self, cmd):
        if cmd in self.cmd:
            self.update_vel_ctrl_seq(0, 0, 0, self.ctrl_seq[-1])
            set_uav_control_input_cmd(self.url_local, cmd=cmd)
            log.success(f"【DroneAgent】 Execute {cmd} successfully!")

    """
    Update speed control sequence
    """
    def update_vel_ctrl_seq(self, forward, leftward, upward, alpha):
        if forward >= self.max_xy_speed or forward <= -self.max_xy_speed:
            log.warn(f"【DroneAgent】forward_speed {forward} m/s invalid(not in the bound [-{self.max_xy_speed}, {self.max_xy_speed}]m/s), auto transfomed!")
            forward = min(self.max_xy_speed, max(forward, -self.max_xy_speed))
        if leftward >= self.max_xy_speed or leftward <= -self.max_xy_speed:
            log.warn(f"【DroneAgent】leftward_speed {leftward} m/s invalid(not in the bound [-{self.max_xy_speed}, {self.max_xy_speed}]m/s), auto transfomed!")
            leftward = min(self.max_xy_speed, max(leftward, -self.max_xy_speed))
        if upward >= self.max_z_speed or upward <= -self.max_z_speed:
            log.warn(f"【DroneAgent】upward_speed {upward} m/s invalid(not in the bound [-{self.max_z_speed}, {self.max_z_speed}]m/s), auto transfomed!")
            upward = min(self.max_z_speed, max(upward, -self.max_z_speed))
        if alpha >= self.max_angel or alpha <= -self.max_angel:
            log.warn(f"【DroneAgent】angel speed {alpha} rad/s invalid(not in the bound [-{self.max_angel}, {self.max_angel}]rad/s), auto transfomed!")
            alpha = min(self.max_angel, max(alpha, -self.max_angel))
        self.ctrl_seq = [forward, leftward, upward, alpha]
        log.success(f"【DroneAgent】change speed to forward{forward:.2f}m/s, leftward{leftward:.2f}m/s, upward{upward:.2f}m/s, yaw{alpha:.2f} degree, successfully")

    def delta_yaw(self):
        delta_yaw = self.yaw - self.ugv_yaw
        delta_yaw = (delta_yaw + math.pi) % (2*math.pi) - math.pi
        if abs(delta_yaw) >= 0.1:
            alpha = -0.1 if delta_yaw > 0 else 0.1
        else:
            alpha = 0
        return alpha / math.pi * 180

    def send_depart(self, speed=3.0, height=10.0):
        self.set_uav_control_cmd_to_local("TAKEOFF")
        while self.pre_pos[2] is None or abs(self.pre_pos[2] - self.pos[2]) <= 0.1:
            log.success(f"[DroneAgent] Waiting for takeoff..")
            time.sleep(0.5)
        self.update_vel_ctrl_seq(0, 0, min(height * 10, max(speed, 0.3)), 0)
        log.success(f"【DroneAgent】depart successfully!")
        log.info(f"【DroneAgent】flying to {height:.2f} m")
        while self.pos[2] is not None and self.pos[2] <= height:
            time.sleep(0.1)
            log.info(f"   【DroneAgent】flying to {height:.2f} m, current{self.pos[2]:.2f}m")
        self.set_uav_control_cmd_to_local("HOVER")
        log.success(f"【DroneAgent】depart to {height:.2f}m successfully!")

    def fly_to_guiding_range(self, height=10, guiding_range=40):
        while not self.stop_flag:
            # Track a point ahead of the UGV so the UAV keeps a stable guiding pose.
            delta_obj_x = guiding_range * math.cos(self.ugv_yaw) - self.pos[0] + self.ugv_pos[0]
            delta_obj_y = guiding_range * math.sin(self.ugv_yaw) - self.pos[1] + self.ugv_pos[1]
            delta_obj_z = height - self.pos[2]
            delta_obj_yaw = self.delta_yaw()
            self.update_vel_ctrl_seq(delta_obj_x, delta_obj_y, delta_obj_z, delta_obj_yaw)
            log.info(f"【DroneAgent】 delta_x {delta_obj_x:.2f} m/s, delta_y {delta_obj_y:.2f} m/s, delta_z {delta_obj_z:.2f} m/s, delta_yaw {delta_obj_yaw:.2f}degree")
            time.sleep(0.2)

    def start_follow_mission(self, height=10, guiding_range=40):
        self.stop_follow_mission()
        if not self.ctrl_process:    
            self.stop_flag = False
            self.ctrl_process = threading.Thread(target=self.fly_to_guiding_range, args=(height, guiding_range))
            self.ctrl_process.start()

    def stop_follow_mission(self):
        if self.ctrl_process:
            self.stop_flag = True
            self.ctrl_process.join()
            self.ctrl_process = None

    def return_to_car_and_land(self):
        self.stop_follow_mission()
        log.error(f"[DroneAgent] Stop follow task")
        self.start_follow_mission(height=2, guiding_range=0)
        while not (self.vx <= 0.01 and self.vy <= 0.01 and abs(self.pre_pos[2] - self.pos[2])):
            log.success(f"[DroneAgent] Waiting to return above vehicle...")
            time.sleep(1)
        log.success(f"[DroneAgent] Returned above vehicle")
        self.set_uav_control_cmd_to_local("LAND")
        while self.pre_pos[2] is None or abs(self.pre_pos[2] - self.pos[2]) <= 0.1:
            log.success(f"[DroneAgent] Waiting to land..")
            time.sleep(0.5)
        log.success(f"[DroneAgent] Landing completed")
        self.departed = False

    def depart_and_start_follow(self, height=10, guiding_range=10):
        self.send_depart(height=2)
        log.success(f"[DroneAgent] Takeoff completed")
        self.start_follow_mission(height=height, guiding_range=guiding_range)
        self.departed = True
        log.success(f"[DroneAgent] Start follow task")
