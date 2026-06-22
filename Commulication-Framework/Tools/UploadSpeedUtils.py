from datetime import datetime


class SpeedCaculator:
    def __init__(self):
        self.upload_times = {}
        self.rec_speed_num = 0
        self.start_time = datetime.now()

    def __getitem__(self, item):
        if not self.upload_times.get(item):
            self.upload_times[item] = datetime.now()
            return 0
        else:
            time_delta = (datetime.now() - self.upload_times[item]).total_seconds()
            s = 1 / time_delta
            self.upload_times[item] = datetime.now()
            return s
