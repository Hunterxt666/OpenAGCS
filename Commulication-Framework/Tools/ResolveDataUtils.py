from datetime import datetime, timedelta


GGA_MODE = {'1': 'GPS±1m', '2': 'GPS±1m', '4': 'RTK±50cm', '5': 'RTK±1cm'}


def resolve_gga_data(gga_data):
    line = str(gga_data).split(',')
    if line[3] != 'N':
        return None
    # Read the 5th field: first 3 digits are longitude (e.g., 117); divide remaining minutes by 60 to get degrees.
    latitude = float(line[2][:2]) + float(line[2][2:]) / 60
    longitude = float(line[4][:3]) + float(line[4][3:]) / 60
    # height = float(line[9])  # Altitude

    star_num = int(line[7])  # Number of satellites in use

    current_time = datetime.now()
    current_date = datetime.utcnow().date()
    utc_time = datetime.strptime(line[1], '%H%M%S.%f')
    combined_utc_time = datetime.combine(current_date, utc_time.time())
    locate_time = combined_utc_time + timedelta(hours=8)
    gga_mode = GGA_MODE.get(line[6], "NA.")
    return {
        "upload_time": current_time, "star_num": star_num, "mode": gga_mode,
        "locate_time": locate_time, "latitude": latitude, "longitude": longitude,
    }  # "height": height,


def resolve_height_data(height_str):
    data = height_str.decode('utf-8').split("Height = ")[1].strip()
    return round(float(data), 2)

