"""Main onboard control loop for the paper's UAV follow mission.

This entrypoint waits until the middleware publishes a valid origin, then keeps
the controller alive and switches between follow-mode and return/land according
to the remote depart flag maintained by the communication framework.
"""

from VehicleAgent.DroneAgent import DroneAgent
import time
from Tools.RequestTools import get_origin_pos
import Tools.LogUtil as log


if __name__ == '__main__':
    url_remote = "REMOTE_URL"  # Replace with the remote middleware URL.
    url_local = "http://127.0.0.1:26969"  # Local onboard API exposed by the middleware.
    while get_origin_pos(url_local) is None:
        log.warn("[Main Process] Origin not set, continue waiting for origin")
        time.sleep(3)
    log.success("[Main Process] Origin set successfully, entering main loop")
    test_drone = DroneAgent(url_remote=url_remote, url_local=url_local)
    while True:
        log.success("[Main Process] Heartbeat...")
        if test_drone.remote_depart_order and not test_drone.depart_flag:
            log.success("[Main Process] Start follow task")
            test_drone.depart_and_start_follow()
        if not test_drone.remote_depart_order and test_drone.depart_flag:
            log.success("[Main Process] Stop follow task")
            test_drone.return_to_car_and_land()
        time.sleep(2)
