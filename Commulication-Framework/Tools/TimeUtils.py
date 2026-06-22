from datetime import datetime


def time_string():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def time_file_name():
    return datetime.now().strftime('%Y%m%d%H%M%S')


def micro_time_file_name():
    return datetime.now().strftime('%Y%m%d%H%M%S%f')


def micro_time_string():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')


def transform_to_str(time):
    return time.strftime('%Y%m%d%H%M%S%f')


def transform_to_time(time_str):
    return datetime.strptime(time_str, "%Y%m%d%H%M%S%f")


def get_time_delta_from_str(start_time, end_time):
    start_time = start_time if isinstance(start_time, str) else transform_to_str(start_time)
    end_time = end_time if isinstance(end_time, str) else transform_to_str(end_time)
    return (transform_to_time(end_time) - transform_to_time(start_time)).total_seconds()
