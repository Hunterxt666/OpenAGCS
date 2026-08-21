import RPi.GPIO as GPIO
import serial
import Tools.LogUtils as log
import time


class LoRaSX126X:
    M0 = 22
    M1 = 27
    # if the header is 0xC0, then the LoRa register settings dont lost when it poweroff, and 0xC2 will be lost.
    cfg_reg = [0xC2, 0x00, 0x09, 0x00, 0x00, 0x00, 0x62, 0x00, 0x12, 0x43, 0x00, 0x00]
    get_reg = bytes(12)
    rssi = False
    addr = 65535
    serial_n = ""
    addr_temp = 0
    start_freq = 410
    offset_freq = 18

    SX126X_UART_BAUDRATE_1200 = 0x00
    SX126X_UART_BAUDRATE_2400 = 0x20
    SX126X_UART_BAUDRATE_4800 = 0x40
    SX126X_UART_BAUDRATE_9600 = 0x60
    SX126X_UART_BAUDRATE_19200 = 0x80
    SX126X_UART_BAUDRATE_38400 = 0xA0
    SX126X_UART_BAUDRATE_57600 = 0xC0
    SX126X_UART_BAUDRATE_115200 = 0xE0

    SX126X_PACKAGE_SIZE_240_BYTE = 0x00
    SX126X_PACKAGE_SIZE_128_BYTE = 0x40
    SX126X_PACKAGE_SIZE_64_BYTE = 0x80
    SX126X_PACKAGE_SIZE_32_BYTE = 0xC0

    SX126X_Power_22dBm = 0x00
    SX126X_Power_17dBm = 0x01
    SX126X_Power_13dBm = 0x02
    SX126X_Power_10dBm = 0x03

    lora_air_speed_dic = {
        1200: 0x01,
        2400: 0x02,
        4800: 0x03,
        9600: 0x04,
        19200: 0x05,
        38400: 0x06,
        62500: 0x07
    }

    lora_power_dic = {
        22: 0x00,
        17: 0x01,
        13: 0x02,
        10: 0x03
    }

    lora_buffer_size_dic = {
        240: SX126X_PACKAGE_SIZE_240_BYTE,
        128: SX126X_PACKAGE_SIZE_128_BYTE,
        64: SX126X_PACKAGE_SIZE_64_BYTE,
        32: SX126X_PACKAGE_SIZE_32_BYTE
    }

    def __init__(self, serial_num, freq, addr, power, air_speed=2400, net_id=0, buffer_size=240, crypt=0):
        self.send_to = None
        self.addr = addr
        self.freq = freq
        self.serial_n = serial_num
        self.power = power
        # Initial the GPIO for M0 and M1 Pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.M0, GPIO.OUT)
        GPIO.setup(self.M1, GPIO.OUT)
        GPIO.output(self.M0, GPIO.LOW)
        GPIO.output(self.M1, GPIO.HIGH)
        # The hardware UART of Pi3B+,Pi4B is /dev/ttyS0
        self.ser = serial.Serial(serial_num, 9600, timeout=2)
        self.ser.flushInput()
        self.set(freq, addr, power, self.rssi, air_speed, net_id, buffer_size, crypt)
        log.success("             [LoRaSX126X] Initialized successfully")

    def set(self, freq, addr, power, rssi, air_speed=2400, net_id=0, buffer_size=240, crypt=0):
        self.send_to = addr
        self.addr = addr
        # We should pull up the M1 pin when sets the module
        GPIO.output(self.M0, GPIO.LOW)
        GPIO.output(self.M1, GPIO.HIGH)
        time.sleep(0.1)

        low_addr = addr & 0xff
        high_addr = addr >> 8 & 0xff
        net_id_temp = net_id & 0xff
        freq_temp = 30
        if freq > 850:
            freq_temp = freq - 850
            self.start_freq = 850
            self.offset_freq = freq_temp
        elif freq > 410:
            freq_temp = freq - 410
            self.start_freq = 410
            self.offset_freq = freq_temp

        air_speed_temp = self.lora_air_speed_dic.get(air_speed, None)

        buffer_size_temp = self.lora_buffer_size_dic.get(buffer_size, None)

        power_temp = self.lora_power_dic.get(power, None)

        if rssi:
            rssi_temp = 0x80
        else:
            rssi_temp = 0x00

        l_crypt = crypt & 0xff
        h_crypt = crypt >> 8 & 0xff

        self.cfg_reg[3] = high_addr
        self.cfg_reg[4] = low_addr
        self.cfg_reg[5] = net_id_temp
        self.cfg_reg[6] = self.SX126X_UART_BAUDRATE_9600 + air_speed_temp
        #
        # it will enable to read noise rssi value when add 0x20 as follow
        #
        self.cfg_reg[7] = buffer_size_temp + power_temp + 0x20
        self.cfg_reg[8] = freq_temp
        #
        # it will output a packet rssi value following received message
        # when enable eighth bit with 06H register(rssi_temp = 0x80)
        #
        self.cfg_reg[9] = 0x43 + rssi_temp
        self.cfg_reg[10] = h_crypt
        self.cfg_reg[11] = l_crypt

        self.ser.flushInput()

        for i in range(2):
            self.ser.write(bytes(self.cfg_reg))
            time.sleep(0.2)
            if self.ser.inWaiting() > 0:
                time.sleep(0.1)
                r_buff = self.ser.read(self.ser.inWaiting())
                if r_buff[0] == 0xC1:
                    pass
                else:
                    pass
                break
            else:
                log.error("             [LoRaSX126X] Init config failed, retrying")
                self.ser.flushInput()
                time.sleep(0.2)

        GPIO.output(self.M0, GPIO.LOW)
        GPIO.output(self.M1, GPIO.LOW)
        time.sleep(0.1)

    def send(self, raw_data):
        GPIO.output(self.M1, GPIO.LOW)
        GPIO.output(self.M0, GPIO.LOW)
        time.sleep(0.1)
        offset_frequency = int(self.freq)-(850 if int(self.freq) > 850 else 410)
        data = (
                bytes([int(self.send_to) >> 8]) + bytes([int(self.send_to) & 0xff]) +
                bytes([offset_frequency]) + bytes([self.addr >> 8]) +
                bytes([self.addr & 0xff]) + bytes([self.offset_freq]) +
                f"{raw_data}\n".encode()
        )
        time.sleep(0.1)
        self.ser.write(data)
        log.success(f"             [LoRaSX126X] Sent {raw_data} successfully")

    def receive(self):
        try:
            if self.ser.inWaiting() > 0:
                # time.sleep(0.1)
                r_buff = self.ser.readline().decode('utf-8').strip()
                log.success(f"             [LoRaSX126X] Received {r_buff} successfully")
                return r_buff
        except Exception as e:
            log.error(f"             [LoRaSX126X] Receive failed, error {e}")
        return None

    def close(self):
        """Release the UART and GPIO resources owned by this LoRa device."""
        try:
            if self.ser is not None and self.ser.is_open:
                self.ser.close()
        finally:
            GPIO.cleanup((self.M0, self.M1))
