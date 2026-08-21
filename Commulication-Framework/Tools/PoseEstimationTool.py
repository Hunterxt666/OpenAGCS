# coding:UTF-8
import threading
import _thread
import time
import struct
import serial
from serial import SerialException
import datetime
import platform
from collections import deque
from dataclasses import dataclass
'''
    Serial port configuration
'''

from abc import abstractmethod, ABCMeta

class IDataProcessor(metaclass=ABCMeta):
    """
    Data processor interface.
    :param metaclass:
    :return:
    """
    onVarChanged = []

    @abstractmethod
    def onOpen(self, deviceModel):
        pass

    @abstractmethod
    def onClose(self):
        pass

    @staticmethod
    def onUpdate(*args):
        pass


class JY901SDataProcessor(IDataProcessor):
    onVarChanged = []
    def onOpen(self, deviceModel):
        pass

    def onClose(self):
        pass

    @staticmethod
    def onUpdate(*args):
        for fun in JY901SDataProcessor.onVarChanged:
            fun(*args)


class SerialConfig:
    # Port
    portName = ''

    # Baud rate
    baud = 9600


@dataclass(frozen=True)
class HeadingSample:
    """One validated angle frame from the pose sensor."""

    yaw: float
    acquired_at: datetime.datetime
    sequence: int


class IProtocolResolver(metaclass=ABCMeta):

    @abstractmethod
    def setConfig(self, config):
        """
        Set configuration.
        :param config: Config data
        :return:
        """
        pass

    @abstractmethod
    def sendData(self, sendData, deviceModel):
        """
        Send data.
        :param sendData: Data to send
        :param deviceModel: Device model
        :return:
        """
        pass

    @abstractmethod
    def readReg(self, regAddr,regCount, deviceModel):
        """
        Read registers.
        :param regAddr: Register address
        :param regCount: Register count
        :param deviceModel: Device model
        :return:
        """
        pass

    @abstractmethod
    def writeReg(self, regAddr,sValue, deviceModel):
        """
        Write registers.
        :param regAddr: Register address
        :param sValue: Value to write
        :param deviceModel: Device model
        :return:
        """
        pass

    @abstractmethod
    def passiveReceiveData(self, data, deviceModel):
        """
        Parse unsolicited data.
        :param data:
        :param deviceModel:
        :return:
        """
        pass

    @abstractmethod
    def unlock(self,deviceModel):
        """
        Unlock.
        :return:
        """
        pass

    @abstractmethod
    def save(self,deviceModel):
        """
        Save.
        :return:
        """
        pass

    @abstractmethod
    def AccelerationCalibration(self,deviceModel):
        """
        Accelerometer calibration.
        :return:
        """
        pass

    @abstractmethod
    def BeginFiledCalibration(self,deviceModel):
        """
        Start magnetic field calibration.
        :return:
        """
        pass

    @abstractmethod
    def EndFiledCalibration(self,deviceModel):
        """
        End magnetic field calibration.
        :return:
        """
        pass


class DeviceModel:
    deviceName = "My Device" # Device name
    ADDR = 0x50 # Device ID
    deviceData = {} # Device data dictionary
    isOpen = False  # Whether device is open
    serialPort = None # Serial port
    serialConfig = SerialConfig() # Serial config
    dataUpdateListener = "" # Update trigger
    dataProcessor = None  # Data processor
    protocolResolver = None # Protocol resolver

    def __init__(self, deviceName, protocolResolver, dataProcessor, dataUpdateListener):
        # print("Initialize device model")
        self.deviceName = deviceName
        self.protocolResolver = protocolResolver
        self.dataProcessor = dataProcessor
        self.dataUpdateListener = dataUpdateListener
        self.deviceData = {}
        self.isOpen = False
        self.serialPort = None
        self.serialConfig = SerialConfig()
        self._data_lock = threading.RLock()
        self._heading_sequence = 0
        self._heading_sample = None
        self._heading_samples = deque()
        self._reader_thread = None

    def setDeviceData(self, key, value):
        """Set device data."""
        with self._data_lock:
            self.deviceData[key] = value

    def getDeviceData(self, key):
        """Get device data."""
        with self._data_lock:
            return self.deviceData.get(key)

    def removeDeviceData(self, key):
        """Delete device data."""
        with self._data_lock:
            del self.deviceData[key]

    def publishHeading(self, yaw, acquired_at=None):
        """Atomically publish a newly decoded heading frame."""
        if acquired_at is None:
            acquired_at = datetime.datetime.now()
        with self._data_lock:
            self._heading_sequence += 1
            self.deviceData["angleZ"] = yaw
            self._heading_sample = HeadingSample(
                yaw=yaw,
                acquired_at=acquired_at,
                sequence=self._heading_sequence,
            )
            self._heading_samples.append(self._heading_sample)

    def getHeadingSample(self):
        """Return the latest immutable heading sample, if one was decoded."""
        with self._data_lock:
            return self._heading_sample

    def getHeadingSamplesAfter(self, sequence=None):
        """Return buffered heading frames newer than ``sequence``."""
        with self._data_lock:
            if sequence is None:
                return tuple(self._heading_samples)
            while (
                self._heading_samples
                and self._heading_samples[0].sequence <= sequence
            ):
                self._heading_samples.popleft()
            return tuple(self._heading_samples)

    def readDataTh(self, threadName, delay):
        """Data read thread."""
        # print("Start " + threadName)
        while self.isOpen:
            # If serial port is open
            try:
                tlen = self.serialPort.inWaiting()
                if (tlen>0):
                    data = self.serialPort.read(tlen)
                    self.onDataReceived(data)
                else:
                    time.sleep(0.005)
            except (SerialException, OSError) as ex:
                if self.isOpen:
                    print(f"Serial read failed: {ex}")
                self.closeDevice()
                break
            except Exception as ex:
                if self.isOpen:
                    print(f"Sensor frame processing failed: {ex}")
                else:
                    break

    def openDevice(self):
        """Open device."""
        # Close port first
        self.closeDevice()
        try:
            self.serialPort = serial.Serial(self.serialConfig.portName, self.serialConfig.baud, timeout=0.5)
            self.isOpen = True
            self._reader_thread = threading.Thread(
                target=self.readDataTh,
                args=("Data-Received-Thread", 10),
                daemon=True,
            )
            self._reader_thread.start()
            return True
        except (SerialException, OSError) as ex:
            self.serialPort = None
            self.isOpen = False
            raise SerialException(
                f"Failed to open {self.serialConfig.portName} "
                f"at {self.serialConfig.baud} baud: {ex}"
            ) from ex

    def closeDevice(self):
        """Close device."""
        self.isOpen = False
        serial_port = self.serialPort
        self.serialPort = None
        if serial_port is not None:
            try:
                serial_port.close()
            except (SerialException, OSError):
                pass
        reader_thread = self._reader_thread
        if (
            reader_thread is not None
            and reader_thread is not threading.current_thread()
            and reader_thread.is_alive()
        ):
            reader_thread.join(timeout=1.0)
        self._reader_thread = None

    def onDataReceived(self, data):
        """On data received."""
        if self.protocolResolver is not None:
            self.protocolResolver.passiveReceiveData(data, self)

    def get_int(self,dataBytes):
        """Signed int conversion = C# BitConverter.ToInt16."""
        #return -(data & 0x8000) | (data & 0x7fff)
        return  int.from_bytes(dataBytes, "little", signed=True)

    def get_unint(self,dataBytes):
        """Unsigned int conversion."""
        return  int.from_bytes(dataBytes, "little")


    def sendData(self, data):
        """Send data."""
        if self.protocolResolver is not None:
            self.protocolResolver.sendData(data, self)

    def readReg(self, regAddr,regCount):
        """Read registers."""
        if self.protocolResolver is not None:
            return self.protocolResolver.readReg(regAddr,regCount, self)
        else:
            return None

    def writeReg(self, regAddr,sValue):
        """Write registers."""
        if self.protocolResolver is not None:
            self.protocolResolver.writeReg(regAddr,sValue, self)

    def unlock(self):
        """Unlock."""
        if self.protocolResolver is not None:
            self.protocolResolver.unlock(self)

    def save(self):
        """Save."""
        if self.protocolResolver is not None:
            self.protocolResolver.save(self)

    def AccelerationCalibration(self):
        """Accelerometer calibration."""
        if self.protocolResolver is not None:
            self.protocolResolver.AccelerationCalibration(self)

    def BeginFiledCalibration(self):
        """Start magnetic field calibration."""
        if self.protocolResolver is not None:
            self.protocolResolver.BeginFiledCalibration(self)

    def EndFiledCalibration(self):
        """End magnetic field calibration."""
        if self.protocolResolver is not None:
            self.protocolResolver.EndFiledCalibration(self)

    def sendProtocolData(self, data):
        """Send data with protocol."""
        if self.protocolResolver is not None:
            self.protocolResolver.sendData(data)

class WitProtocolResolver(IProtocolResolver):
    TempBytes=[]         # Temporary data buffer
    PackSize = 11        # Packet size
    gyroRange = 2000.0   # Gyro range
    accRange = 16.0      # Acceleration range
    angleRange = 180.0   # Angle range
    TempFindValues=[]    # Data returned from register reads

    def __init__(self):
        self.TempBytes = []
        self.TempFindValues = []

    def setConfig(self, deviceModel):
        pass

    def sendData(self, sendData, deviceModel):
        success_bytes = deviceModel.serialPort.write(sendData)
    def passiveReceiveData(self, data, deviceModel):
        """
        Process received data.
        :param data: Serial data
        :param deviceModel: Device model
        :return:
        """
        global TempBytes
        for val in data:
            self.TempBytes.append(val)
            if (self.TempBytes[0]!=0x55):                   # Not starting with marker 0x55
                del self.TempBytes[0]                       # Drop the first byte
                continue
            if (len(self.TempBytes)>1):
                if (((self.TempBytes[1] - 0x50 >=0 and self.TempBytes[1] - 0x50 <=11) or self.TempBytes[1]==0x5f)==False):   # Second byte not in 0x50~0x5a or not equal to 0x5f
                    del self.TempBytes[0]                   # Drop the first byte
                    continue
            if (len(self.TempBytes) == self.PackSize):      # Full packet length
                CheckSum = 0                                # Checksum (sum)
                for i in range(0,self.PackSize-1):
                    CheckSum+=self.TempBytes[i]
                if (CheckSum&0xff==self.TempBytes[self.PackSize-1]):  # Checksum ok
                    if (self.TempBytes[1] == 0x50):                   # Chip time packet
                        self.get_chiptime(self.TempBytes, deviceModel) # Compute chip time data
                    elif (self.TempBytes[1]==0x51):                    # Acceleration packet
                        self.get_acc(self.TempBytes,deviceModel)       # Compute acceleration data
                    elif(self.TempBytes[1]==0x52):                    # Gyro packet
                        self.get_gyro(self.TempBytes,deviceModel)     # Compute gyro data
                    elif(self.TempBytes[1]==0x53):                    # Angle packet
                        self.get_angle(self.TempBytes,deviceModel)    # Compute angle data
                    elif(self.TempBytes[1]==0x54):                    # Magnetic field packet
                        self.get_mag(self.TempBytes, deviceModel)     # Compute magnetic field data
                        deviceModel.dataProcessor.onUpdate(deviceModel) # Trigger data update event
                    elif(self.TempBytes[1]==0x57):                    # Latitude/longitude packet
                        self.get_lonlat(self.TempBytes, deviceModel)     # Compute lat/lon data
                        deviceModel.dataProcessor.onUpdate(deviceModel) # Trigger data update event
                    elif(self.TempBytes[1]==0x58):                    # GPS packet
                        self.get_gps(self.TempBytes, deviceModel)     # Compute GPS data
                        deviceModel.dataProcessor.onUpdate(deviceModel) # Trigger data update event
                    elif(self.TempBytes[1]==0x59):                    # Quaternion packet
                        self.get_four_elements(self.TempBytes, deviceModel)     # Compute quaternion data
                        deviceModel.dataProcessor.onUpdate(deviceModel) # Trigger data update event
                    elif(self.TempBytes[1]==0x5f):           # Return specified register reads
                        self.get_find(self.TempBytes,deviceModel)
                    self.TempBytes=[]                        # Clear buffer
                else:                                        # Checksum failed
                    del self.TempBytes[0]                    # Drop the first byte

    def get_readbytes(self,regAddr):
        """
        Build read command.
        :param regAddr: Register address
        :return:
        """
        return [0xff, 0xaa,0x27, regAddr & 0xff, regAddr >> 8]

    def get_writebytes(self,regAddr,sValue):
        """
        Build write command.
        :param regAddr: Register address
        :param sValue: Value to write
        :return:
        """
        return [0xff, 0xaa, regAddr, sValue & 0xff, sValue >> 8]

    def get_acc(self,datahex, deviceModel):
        """
        Compute acceleration and temperature.
        :param datahex: Raw data packet
        :param deviceModel: Device model
        :return:
        """
        axl = datahex[2]
        axh = datahex[3]
        ayl = datahex[4]
        ayh = datahex[5]
        azl = datahex[6]
        azh = datahex[7]

        tempVal = (datahex[9] << 8 | datahex[8])
        acc_x = (axh << 8 | axl) / 32768.0 * self.accRange
        acc_y = (ayh << 8 | ayl) / 32768.0 * self.accRange
        acc_z = (azh << 8 | azl) / 32768.0 * self.accRange
        if acc_x >= self.accRange:
            acc_x -= 2 * self.accRange
        if acc_y >= self.accRange:
            acc_y -= 2 * self.accRange
        if acc_z >= self.accRange:
            acc_z -= 2 * self.accRange

        deviceModel.setDeviceData("accX", round(acc_x, 4))     # Set device accel X
        deviceModel.setDeviceData("accY", round(acc_y, 4))     # Set device accel Y
        deviceModel.setDeviceData("accZ", round(acc_z, 4))     # Set device accel Z
        temperature = round(tempVal / 100.0, 2)                                           # Compute temperature, keep two decimals
        deviceModel.setDeviceData("temperature", temperature)                             # Set device temperature

    def get_gyro(self,datahex, deviceModel):
        """
        Compute gyro.
        :param datahex: Raw data packet
        :param deviceModel: Device model
        :return:
        """
        wxl = datahex[2]
        wxh = datahex[3]
        wyl = datahex[4]
        wyh = datahex[5]
        wzl = datahex[6]
        wzh = datahex[7]

        gyro_x = (wxh << 8 | wxl) / 32768.0 * self.gyroRange
        gyro_y = (wyh << 8 | wyl) / 32768.0 * self.gyroRange
        gyro_z = (wzh << 8 | wzl) / 32768.0 * self.gyroRange
        if gyro_x >= self.gyroRange:
            gyro_x -= 2 * self.gyroRange
        if gyro_y >= self.gyroRange:
            gyro_y -= 2 * self.gyroRange
        if gyro_z >= self.gyroRange:
            gyro_z -= 2 * self.gyroRange

        deviceModel.setDeviceData("gyroX", round(gyro_x, 4))  # Set device gyro X
        deviceModel.setDeviceData("gyroY", round(gyro_y, 4))  # Set device gyro Y
        deviceModel.setDeviceData("gyroZ", round(gyro_z, 4))  # Set device gyro Z

    def get_angle(self,datahex, deviceModel):
        """
        Compute angles.
        :param datahex: Raw data packet
        :param deviceModel: Device model
        :return:
        """
        rxl = datahex[2]
        rxh = datahex[3]
        ryl = datahex[4]
        ryh = datahex[5]
        rzl = datahex[6]
        rzh = datahex[7]

        angle_x = (rxh << 8 | rxl) / 32768.0 * self.angleRange
        angle_y = (ryh << 8 | ryl) / 32768.0 * self.angleRange
        angle_z = (rzh << 8 | rzl) / 32768.0 * self.angleRange
        if angle_x >= self.angleRange:
            angle_x -= 2 * self.angleRange
        if angle_y >= self.angleRange:
            angle_y -= 2 * self.angleRange
        if angle_z >= self.angleRange:
            angle_z -= 2 * self.angleRange

        deviceModel.setDeviceData("angleX", round(angle_x, 3))  # Set device angle X
        deviceModel.setDeviceData("angleY", round(angle_y, 3))  # Set device angle Y
        deviceModel.publishHeading(
            round(angle_z, 3), acquired_at=datetime.datetime.now()
        )

    def get_mag(self,datahex, deviceModel):
        """
        Compute magnetic field.
        :param datahex: Raw data packet
        :param deviceModel: Device model
        :return:
        """
        _x = deviceModel.get_int(bytes([datahex[2],datahex[3]]))
        _y = deviceModel.get_int(bytes([datahex[4],datahex[5]]))
        _z = deviceModel.get_int(bytes([datahex[6],datahex[7]]))

        deviceModel.setDeviceData("magX", round(_x, 0))   # Set device mag X
        deviceModel.setDeviceData("magY", round(_y, 0))   # Set device mag Y
        deviceModel.setDeviceData("magZ", round(_z, 0))   # Set device mag Z

    def get_lonlat(self,datahex, deviceModel):
        """
        Compute longitude/latitude.
        :param datahex: Raw data packet
        :param deviceModel: Device model
        :return:
        """

        lon = deviceModel.get_unint(bytes([datahex[2],datahex[3],datahex[4],datahex[5]]))
        lat = deviceModel.get_unint(bytes([datahex[6],datahex[7],datahex[8],datahex[9]]))
        #(lon / 10000000 + ((double)(lon % 10000000) / 1e5 / 60.0)).ToString("f8")
        tlon = int(lon / 10000000) + ((lon % 10000000) / 100000 / 60)
        tlat = int(lat / 10000000) + ((lat % 10000000) / 100000 / 60)

        deviceModel.setDeviceData("lon", round(tlon, 8))   # Set device longitude
        deviceModel.setDeviceData("lat", round(tlat, 8))   # Set device latitude

    def get_gps(self,datahex, deviceModel):
        """
        Compute GPS.
        :param datahex: Raw data packet
        :param deviceModel: Device model
        :return:
        """
        Height = deviceModel.get_int(bytes([datahex[2],datahex[3]])) / 10.0   # Height
        Yaw = deviceModel.get_int(bytes([datahex[4],datahex[5]])) / 100.0     # Heading
        Speed = deviceModel.get_unint(bytes([datahex[6],datahex[7],datahex[8],datahex[9]])) / 1e3            # Nautical miles

        deviceModel.setDeviceData("Height", round(Height, 3))   # Set device height
        deviceModel.setDeviceData("Yaw", round(Yaw, 2))   # Set device heading
        deviceModel.setDeviceData("Speed", round(Speed, 3))   # Set device speed

    def get_four_elements(self,datahex, deviceModel):
        """
        Compute quaternion.
        :param datahex: Raw data packet
        :param deviceModel: Device model
        :return:
        """
        q1 = deviceModel.get_int(bytes([datahex[2],datahex[3]])) / 32768.0
        q2 = deviceModel.get_int(bytes([datahex[4],datahex[5]])) / 32768.0
        q3 = deviceModel.get_int(bytes([datahex[6],datahex[7]])) / 32768.0
        q4 = deviceModel.get_int(bytes([datahex[8],datahex[9]])) / 32768.0

        deviceModel.setDeviceData("q1", round(q1, 5))   # Set device element q1
        deviceModel.setDeviceData("q2", round(q2, 5))   # Set device element q2
        deviceModel.setDeviceData("q3", round(q3, 5))   # Set device element q3
        deviceModel.setDeviceData("q4", round(q4, 5))  # Set device element q4

    def get_chiptime(self,datahex, deviceModel):
        """
        Compute chip time.
        :param datahex: Raw data packet
        :param deviceModel: Device model
        :return:
        """
        tempVals = []      # Temp values
        for i in range(0,4):
            tIndex = 2 + i * 2
            tempVals.append(datahex[tIndex+1] << 8 | datahex[tIndex])

        _year = 2000 + (tempVals[0] & 0xff)      # Year
        _moth = ((tempVals[0] >> 8) & 0xff)      # Month
        _day = (tempVals[1] & 0xff)              # Day
        _hour = ((tempVals[1] >> 8) & 0xff)      # Hour
        _minute = (tempVals[2] & 0xff)           # Minute
        _second = ((tempVals[2] >> 8) & 0xff)    # Second
        _millisecond = tempVals[3]               # Millisecond
        deviceModel.setDeviceData("Chiptime",
                                  str(_year) + "-" + str(_moth) + "-" + str(_day) + " " + str(_hour) + ":" + str(
                                      _minute) + ":" + str(_second) + "." + str(_millisecond))  # Set device chip time

    def readReg(self, regAddr,regCount, deviceModel):
        """
        Read registers.
        :param regAddr: Register address
        :param regCount: Register count
        :param deviceModel: Device model
        :return:
        """
        tempResults = []                      # Return data
        readCount = int(regCount/4)           # Compute read count from register count
        if (regCount % 4>0):
            readCount+=1
        for n in range(0,readCount):
            self.TempFindValues = []  # Clear buffer
            tempBytes = self.get_readbytes(regAddr + n * 4)             # Build read command
            success_bytes = deviceModel.serialPort.write(tempBytes)     # Write data
            for i in range(0,20): # Timeout 1s
                time.sleep(0.05)  # Sleep 50 ms
                if (len(self.TempFindValues)>0):    # Register values returned
                    for j in range(0,len(self.TempFindValues)):
                        if (len(tempResults) < regCount):
                            tempResults.append(self.TempFindValues[j])
                        else:
                            break
                    break
        return tempResults

    def writeReg(self, regAddr,sValue, deviceModel):
        """
        Write registers.
        :param regAddr: Register address
        :param sValue: Value to write
        :param deviceModel: Device model
        :return:
        """
        tempBytes = self.get_writebytes(regAddr,sValue)                  # Build write command
        success_bytes = deviceModel.serialPort.write(tempBytes)          # Write register
    def unlock(self, deviceModel):
        """
        Unlock.
        :return:
        """
        tempBytes = self.get_writebytes(0x69, 0xb588)                    # Build write command
        success_bytes = deviceModel.serialPort.write(tempBytes)          # Write register

    def save(self, deviceModel):
        """
        Save.
        :param deviceModel: Device model
        :return:
        """
        tempBytes = self.get_writebytes(0x00, 0x00)                      # Build write command
        success_bytes = deviceModel.serialPort.write(tempBytes)          # Write register

    def AccelerationCalibration(self,deviceModel):
        """
        Accelerometer calibration.
        :param deviceModel: Device model
        :return:
        """
        self.unlock(deviceModel)                                         # Unlock
        time.sleep(0.1)                                                  # Sleep 100 ms
        tempBytes = self.get_writebytes(0x01, 0x01)                      # Build write command
        success_bytes = deviceModel.serialPort.write(tempBytes)          # Write register
        time.sleep(5.5)                                                  # Sleep 5500 ms

    def BeginFiledCalibration(self,deviceModel):
        """
        Start magnetic field calibration.
        :param deviceModel: Device model
        :return:
        """
        self.unlock(deviceModel)                                         # Unlock
        time.sleep(0.1)                                                  # Sleep 100 ms
        tempBytes = self.get_writebytes(0x01, 0x07)                      # Build write command for magnetic calibration
        success_bytes = deviceModel.serialPort.write(tempBytes)          # Write register


    def EndFiledCalibration(self,deviceModel):
        """
        End magnetic field calibration.
        :param deviceModel: Device model
        :return:
        """
        self.unlock(deviceModel)                                         # Unlock
        time.sleep(0.1)                                                  # Sleep 100 ms
        self.save(deviceModel)                                           # Save

    def get_find(self,datahex, deviceModel):
        """
        Compute specified register values.
        :param datahex: Raw data packet
        :param deviceModel: Device model
        :return:
        """
        t0l = datahex[2]
        t0h = datahex[3]
        t1l = datahex[4]
        t1h = datahex[5]
        t2l = datahex[6]
        t2h = datahex[7]
        t3l = datahex[8]
        t3h = datahex[9]

        val0 = (t0h << 8 | t0l)
        val1 = (t1h << 8 | t1l)
        val2 = (t2h << 8 | t2l)
        val3 = (t3h << 8 | t3l)
        self.TempFindValues.extend([val0,val1,val2,val3])

class Sensor:
    def __init__(self, port_name):
        self.device = DeviceModel(
            "3D-pose-estimation-tool",
            WitProtocolResolver(),
            JY901SDataProcessor(),
            "51_0"
        )
        self.device.serialConfig.portName = port_name
        self.device.serialConfig.baud = 9600 
        self.device.openDevice() 

    @property
    def is_open(self):
        return self.device.isOpen

    @property
    def heading_sample(self):
        """Latest validated angle frame with acquisition time and sequence."""
        return self.device.getHeadingSample()

    def heading_samples_after(self, sequence=None):
        """Buffered validated angle frames newer than ``sequence``."""
        return self.device.getHeadingSamplesAfter(sequence)

    @property
    def yaw(self):
        sample = self.heading_sample
        return None if sample is None else sample.yaw

    @property
    def yaw_sequence(self):
        sample = self.heading_sample
        return None if sample is None else sample.sequence

    @property
    def yaw_acquired_at(self):
        sample = self.heading_sample
        return None if sample is None else sample.acquired_at

    def close(self):
        self.device.closeDevice()
