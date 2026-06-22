import mysql.connector
from Tools.TimeUtils import micro_time_string
import Tools.LogUtils as log
import redis
import json


def commit_sql(sql, sql_config):
    try:
        conn = mysql.connector.connect(
            host=sql_config['host'], user=sql_config['user'], password=sql_config['pw'],
            database=sql_config['db_name'], port=sql_config['port'],
            connection_timeout=2,  # Connection timeout (seconds)
            # read_timeout=0.5,  # Read timeout (seconds)
            # write_timeout=0.5  # Write timeout (seconds)
        )
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        log.error(f"                  [DB Utils] Failed to execute {sql}")


def create_rtk_data_table(table_name, sql_config):
    sql = f"""
    CREATE TABLE {table_name}(  
        upload_time DATETIME(6) NOT NULL PRIMARY KEY,
        locate_time  DATETIME(6),
        gga_mode CHAR(10),
        longitude DOUBLE(15, 12),
        latitude DOUBLE(15, 12),
        star_num TINYINT UNSIGNED
    );
    """
    # altitude FLOAT,
    commit_sql(sql, sql_config)


def create_height_data_table(table_name, sql_config):
    sql = f"""
    CREATE TABLE {table_name}(  
        upload_time DATETIME(6) NOT NULL PRIMARY KEY,
        height  Float
    );
    """
    # altitude FLOAT,
    commit_sql(sql, sql_config)

# Add orientation data table
def create_orientation_data_table(table_name, sql_config):
    sql = f"""
    CREATE TABLE {table_name}(  
        upload_time DATETIME(6) NOT NULL PRIMARY KEY,
        orientation  Float
    );
    """
    # orientation FLOAT,
    commit_sql(sql, sql_config)


def upload_rtk_data(rtk_data, table_name, sql_config):
    add_data_sql = f"""
    INSERT INTO {table_name}(upload_time, locate_time, gga_mode, longitude, latitude, star_num) 
    VALUES ('{rtk_data['upload_time']}', '{rtk_data['locate_time']}', '{rtk_data['mode']}', {rtk_data['longitude']}, {rtk_data['latitude']}, {rtk_data['star_num']})
    """
    # altitude, {rtk_data['height']},
    commit_sql(add_data_sql, sql_config)


def upload_height_data(time, data, table_name, sql_config):
    add_data_sql = f"""
    INSERT INTO {table_name}(upload_time, height) 
    VALUES ('{time}', {data})
    """
    commit_sql(add_data_sql, sql_config)


def upload_orientation_data(time, data, table_name, sql_config):
    add_data_sql = f"""
    INSERT INTO {table_name}(upload_time, orientation) 
    VALUES ('{time}', {data})
    """
    commit_sql(add_data_sql, sql_config)
    

def create_photo_data_table(table_name, sql_config):
    create_table_sql = f"""
        CREATE TABLE {table_name} (
            upload_time DATETIME(6) NOT NULL PRIMARY KEY,
            path TEXT
        );
    """
    commit_sql(create_table_sql, sql_config)


def upload_photo_data(table_name, path, sql_config):
    add_data_sql = f"""
    INSERT INTO {table_name} (upload_time, path)
    VALUES ('{micro_time_string()}', '{path}')
    """
    commit_sql(add_data_sql, sql_config)


class RedisDict:
    def __init__(self, host="localhost", port=6379, db=0):
        """Initialize Redis client."""
        self.redis_client = redis.StrictRedis(host=host, port=port, db=db, decode_responses=True)

    def _get_key(self, key: str) -> any:
        """Get a key from Redis and handle serialized values."""
        value = self.redis_client.get(key)
        if value == "true":
            return True
        elif value == "false":
            return False
        elif value == "null" or value == "":
            return None
        try:
            # Try to convert string to float or int
            if '.' in value:
                return float(value)  # Convert to float
            else:
                return int(value)  # Convert to int
        except Exception:
            pass  # If not numeric, keep raw string
        try:
            # Try to parse JSON string data
            return json.loads(value)
        except Exception:
            return value  # If JSON parse fails, return raw string

    def _set_key(self, key: str, value: any) -> None:
        """Set a key/value in Redis and handle serialized values."""
        if isinstance(value, (dict, list)):
            value = json.dumps(value)  # Serialize dict/list to JSON
        elif isinstance(value, bool):  # Special handling for bool
            value = "true" if value else "false"
        elif value is None:
            value = "null"
        self.redis_client.set(key, value)

    def __getitem__(self, key: str) -> any:
        """Get a value from Redis (dict-style)."""
        value = self._get_key(key)
        if value is None:
            return None
        return value

    def __setitem__(self, key: str, value: any) -> None:
        """Set a value in Redis (dict-style)."""
        self._set_key(key, value)

    def __delitem__(self, key: str) -> None:
        """Delete a value in Redis (dict-style)."""
        self.redis_client.delete(key)

    def __contains__(self, key: str) -> bool:
        """Check if a key exists in Redis (dict-style)."""
        return self.redis_client.exists(key)

    def get(self, key: str, default=None) -> any:
        """Get a value; return default if missing."""
        return self._get_key(key) or default

    def keys(self):
        """Get all Redis keys."""
        return self.redis_client.keys()

    def pop(self, key: str, default=None) -> any:
        """Pop a key from Redis; return default if missing."""
        value = self._get_key(key)
        if value is not None:
            self.redis_client.delete(key)
        return value or default

    def init_keys(self, data: dict):
        """Initialize multiple Redis keys."""
        for key, val in data.items():
            self._set_key(key, val)

    def __repr__(self):
        """Provide a dict-like string representation."""
        return f"RedisDict({self.redis_client.keys()})"
