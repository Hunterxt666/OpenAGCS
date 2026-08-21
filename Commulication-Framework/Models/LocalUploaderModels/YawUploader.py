from dataclasses import dataclass
from datetime import datetime
from threading import Event, Thread

from Tools.ConfigUtils import read_config
import Tools.LogUtils as log
from Tools.DBUtils import create_orientation_data_table, upload_orientation_data
from Tools.PoseEstimationTool import Sensor
from Tools.UploadSpeedUtils import SpeedCaculator
from Tools.RequestTools import send_orientation
from Tools.HeadingFilter import AdaptiveHeadingKalmanFilter


@dataclass(frozen=True)
class FilteredHeadingSample:
    """A filtered heading that retains its source-frame metadata."""

    sequence: int
    acquired_at: datetime
    yaw: float


class YawUploader:
    def __init__(self, time_str, config_path, agent, remote_url, local_url):
        log.info("  [Yaw Uploader] Initializing..")
        config = read_config(config_path)
        filter_config = config.get("HeadingFilter", {})
        self.speed_test = SpeedCaculator()
        self.agent = agent
        self.mission_id = time_str
        self.yaw_data = None
        self.raw_yaw = None
        self.pre_data = {
            "send_local": None,
            "send_remote": None,
            "send_db": None,
        }
        self.pending_data = {
            "send_local": None,
            "send_remote": None,
        }
        self.last_sensor_sequence = None
        self.remote_url = remote_url
        self.local_url = local_url
        self.stop_event = Event()
        self.stop_flag = False
        self.task_list = []
        self.yaw_filter = AdaptiveHeadingKalmanFilter(
            process_variance=filter_config.get("process_variance", 0.03),
            measurement_variance=filter_config.get(
                "measurement_variance", 2.742e-3
            ),
            lower_threshold=filter_config.get(
                "lower_threshold", 0.6108652381980153
            ),
            upper_threshold=filter_config.get(
                "upper_threshold", 2.443460952792061
            ),
            covariance_inflation=filter_config.get("covariance_inflation", 10.0),
            initial_covariance=filter_config.get("initial_covariance", 1.0),
        )
        log.info("    [Yaw Uploader] Initializing module serial port..")
        try:
            self.serial = Sensor(config['SerialConfig']['port'])
        except Exception as exc:
            log.error(
                "    [Yaw Uploader] Failed to open heading sensor on "
                f"{config['SerialConfig']['port']}: {exc}"
            )
            raise
        log.success("    [Yaw Uploader] Serial port connected")
        # self.table_name = f"{time_str}_{agent}_yaw_data"
        # self.sql_config = config['DBconfig']
        # log.info(f"    [Yaw Uploader] Initializing SQL, creating yaw table {self.table_name}..")
        # create_orientation_data_table(self.table_name, self.sql_config)
        # log.success(f"    [Yaw Uploader] SQL initialized, yaw table {self.table_name} created")
        self.start_mission()
        log.success("  [Yaw Uploader] Initialization complete, starting upload")

    def start_mission(self):
        log.info("    [Yaw Uploader] Preparing to start upload tasks...")
        self.task_list.append(
            Thread(target=self.get_yaw_str, name="yaw-sensor-reader")
        )
        self.task_list.append(
            Thread(target=self.upload_yaw_data_to_local, name="yaw-local-uploader")
        )
        self.task_list.append(
            Thread(target=self.upload_yaw_data_to_remote, name="yaw-remote-uploader")
        )
        # self.task_list.append(Thread(target=self.upload_yaw_data_to_db))
        for t in self.task_list:
            t.start()
        log.success("    [Yaw Uploader] Upload tasks started")

    def process_heading_sample(self, sample):
        """Filter one sensor frame once and retain its acquisition timestamp."""
        if (
            sample is None
            or (
                self.last_sensor_sequence is not None
                and sample.sequence <= self.last_sensor_sequence
            )
        ):
            return False

        filtered_yaw = self.yaw_filter.update_degrees(sample.yaw)
        self.raw_yaw = sample.yaw
        self.yaw_data = FilteredHeadingSample(
            sequence=sample.sequence,
            acquired_at=sample.acquired_at,
            yaw=filtered_yaw,
        )
        self.last_sensor_sequence = sample.sequence
        return True

    def get_yaw_str(self):
        log.info("      [Yaw Uploader] [Get yaw data] starting...")
        while not self.stop_flag:
            try:
                samples = self.serial.heading_samples_after(
                    self.last_sensor_sequence
                )
                for sample in samples:
                    if self.process_heading_sample(sample):
                        current = self.yaw_data
                        log.success(
                            f"      [Yaw Uploader] [Get yaw data] success, "
                            f"rate {self.speed_test['get_yaw_data']:.2f} ops/s, "
                            f"frame {current.sequence}, "
                            f"raw {self.raw_yaw:.2f} deg, "
                            f"filtered {current.yaw:.2f} deg"
                        )
            except Exception as e:
                log.error(f"      [Yaw Uploader] [Get yaw data] error: {e}")
            self.stop_event.wait(0.05)
        log.error("      [Yaw Uploader] [Get yaw data] exiting")

    def send_latest_orientation(self, destination, url):
        """Send the newest sample and acknowledge it only after HTTP success."""
        pending_data = getattr(self, "pending_data", None)
        if pending_data is None:
            self.pending_data = {}
            pending_data = self.pending_data
        current = pending_data.get(destination)
        if current is None:
            current = self.yaw_data
            if (
                current is None
                or self.pre_data[destination] == current.sequence
            ):
                return None
            pending_data[destination] = current

        sent = send_orientation(
            url=url,
            time=current.acquired_at,
            orientation=current.yaw,
            agent=self.agent,
            mission_id=getattr(self, "mission_id", None),
        )
        if sent:
            self.pre_data[destination] = current.sequence
            pending_data[destination] = None
        return sent

    def upload_yaw_data_to_local(self):
        log.info("      [Yaw Uploader] [Local yaw upload] starting...")
        while not self.stop_flag:
            try:
                sent = self.send_latest_orientation("send_local", self.local_url)
                if sent:
                    log.success(
                        "        [Yaw Uploader] [Local yaw upload] succeeded, "
                        f"rate {self.speed_test['get_local_yaw_data']:.2f} ops/s, "
                        f"yaw {self.yaw_data.yaw} deg"
                    )
                elif sent is False:
                    log.warn(
                        "        [Yaw Uploader] [Local yaw upload] failed; "
                        "the latest frame will be retried"
                    )
                    self.stop_event.wait(0.5)
            except Exception as e:
                log.error(f"        [Yaw Uploader] [Local yaw upload] error {e}")
                self.stop_event.wait(1)
            self.stop_event.wait(0.05)
        log.error("      [Yaw Uploader] [Local yaw upload] exiting")

    def upload_yaw_data_to_remote(self):
        log.info("      [Yaw Uploader] [Remote yaw upload] starting...")
        while not self.stop_flag:
            try:
                sent = self.send_latest_orientation(
                    "send_remote", self.remote_url
                )
                if sent:
                    log.success(
                        "        [Yaw Uploader] [Remote yaw upload] succeeded, "
                        f"rate {self.speed_test['get_remote_yaw_data']:.2f} ops/s, "
                        f"yaw {self.yaw_data.yaw} deg"
                    )
                elif sent is False:
                    log.warn(
                        "        [Yaw Uploader] [Remote yaw upload] failed; "
                        "the latest frame will be retried"
                    )
                    self.stop_event.wait(0.5)
            except Exception as e:
                log.error(f"        [Yaw Uploader] [Remote yaw upload] error {e}")
                self.stop_event.wait(1)
            self.stop_event.wait(0.05)
        log.error("      [Yaw Uploader] [Remote yaw upload] exiting")

    def upload_yaw_data_to_db(self):
        log.info("      [Yaw Uploader] [DB yaw upload] starting...")
        while not self.stop_flag:
            try:
                current = self.yaw_data
                if (
                    current is not None
                    and self.pre_data["send_db"] != current.sequence
                ):
                    upload_orientation_data(
                        current.acquired_at,
                        current.yaw,
                        self.table_name,
                        self.sql_config,
                    )
                    log.success(
                        "        [Yaw Uploader] [DB yaw upload] succeeded, "
                        f"rate {self.speed_test['get_db_yaw_data']:.2f} ops/s, "
                        f"yaw {current.yaw} deg"
                    )
                    self.pre_data["send_db"] = current.sequence
            except Exception as e:
                log.error(f"        [Yaw Uploader] [DB yaw upload] error {e}")
                self.stop_event.wait(1)
            self.stop_event.wait(0.05)
        log.error("      [Yaw Uploader] [DB yaw upload] exiting")

    def stop(self):
        if self.stop_flag:
            return
        self.stop_flag = True
        self.stop_event.set()
        self.serial.close()
        log.info("  [Yaw Uploader] Stopping, waiting for tasks to finish...")
        for t in self.task_list:
            t.join(timeout=2.0)
            if t.is_alive():
                log.warn(f"  [Yaw Uploader] Task {t.name} did not stop in time")
        log.error("  [Yaw Uploader] Stopped, upload ended")


if __name__ == "__main__":
    import sys
    location_model = YawUploader(
        config_path=sys.argv[1], time_str=sys.argv[2], agent=sys.argv[3],
        remote_url=sys.argv[4], local_url=sys.argv[5]
    )
    log.success("  [Yaw Uploader] Started. Press any key to exit.. \n")
    input()
    location_model.stop()
    exit(3)
