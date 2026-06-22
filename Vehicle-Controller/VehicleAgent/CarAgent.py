import rospy
from geometry_msgs.msg import Twist
from gazebo_msgs.msg import ModelStates
import Tools.LogUtil as log
from Tools.PosUtil import resolve_pos_data
import threading
import numpy as np
import time



class CarAgent:
    def __init__(self, node_name, max_speed=20, max_angel=1, other_name=None):
        log.info(f"【CarAgent>{node_name}】init...")
        # init model data
        self.name = node_name
        self.pos = [None] * 3
        self.yaw = 0
        self.max_angel = max_angel
        self.max_speed = max_speed
        self.other_name = other_name
        self.other_pos = [[None, None, None]] * len(other_name) if other_name else None

        # init ros
        rospy.init_node(f'{self.name}_control_ugv', anonymous=True, disable_signals=True)
        self.ros_vel_ctrl_topic = rospy.Publisher(f'/{node_name}/cmd_vel', Twist, queue_size=1)
        self.ros_state_topic = rospy.Subscriber(f'/gazebo/model_states', ModelStates, self.get_msg_from_ros_topic)
        self.ros_thread = threading.Thread(target=rospy.spin)
        self.ros_thread.start()
        self.ctrl_seq = Twist()
        log.success(f"【CarAgent>{self.name}】create successfully!")
    
    def get_msg_from_ros_topic(self, msg):
        pos_data = resolve_pos_data(self.name, msg)
        self.pos = np.array(pos_data[0:3])
        self.yaw = pos_data[-1]
        if self.other_name:
            for i, n in enumerate(self.other_name):
                self.other_pos[i] = np.array(resolve_pos_data(n, msg)[0:3])
    
    def send_cmd(self, f_spead, angle_spead):
        log.info(f"【CarAgent>{self.name}】calling change state to forward speed {f_spead}m/s, alpha {angle_spead} rad/s")
        if f_spead >= self.max_speed or f_spead <= -self.max_speed:
            log.warn(f"【CarAgent>{self.name}】forward_speed {f_spead} m/s invalid(not in the bound [-{self.max_speed}, {self.max_speed}]m/s), auto transfomed!")
            f_spead = min(self.max_speed, max(f_spead, -self.max_speed))
        if angle_spead >= self.max_angel or angle_spead <= -self.max_angel:
            log.warn(f"【CarAgent>{self.name}】angel speed {angle_spead} rad/s invalid(not in the bound [-{self.max_angel}, {self.max_angel}]rad/s), auto transfomed!")
            angle_spead = min(self.max_angel, max(angle_spead, -self.max_angel))
        self.ctrl_seq.linear.x = f_spead
        self.ctrl_seq.angular.z =  angle_spead
        self.ros_vel_ctrl_topic.publish(self.ctrl_seq)
        log.success(f"【CarAgent>{self.name}】publish forward speed {f_spead}m/s, alpha {angle_spead} rad/s successfully!")

    def send_cmd_timing(self, f_spead, angle_spead, DrivingTime):
        self.send_cmd(f_spead,angle_spead)
        time.sleep(DrivingTime)
    
    def force_stop(self):
        self.ctrl_seq.linear.x = 0
        self.ctrl_seq.angular.z =  0
        self.ros_vel_ctrl_topic.publish(self.ctrl_seq)
        log.success(f"【CarAgent>{self.name}】stopped forward speed 0 m/s, alpha 0 rad/s successfully!")


    @property
    def x(self):
        return self.pos[0]
    
    @property
    def y(self):
        return self.pos[1]
    
    @property
    def z(self):
        return self.pos[2]
    
    @property
    def forward_speed(self):
        return self.ctrl_seq.linear.x

    @property
    def angel_speed(self):
        return self.ctrl_seq.angular.z

    def get_other_pos(self, other_name):
        if other_name not in self.other_name:
            log.error(f"【CarAgent>{self.name}】{other_name} not in list!")
            return
        idx = self.other_name.index(other_name)
        return self.other_pos[idx]