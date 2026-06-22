import cv2
from picamera2 import Picamera2
frame = {
    "480P": [640, 480], "720P": [1280, 720],
    "1080P": [1920, 1080], "2K": [2560, 1440],
    "4K": [4096, 2160]
}
display = "480P"


def take_picture(path, port_path):
    cap = cv2.VideoCapture(port_path)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1080)
    ret, frame = cap.read()
    cv2.imwrite(path, frame)
    cap.release()


class Camera:
    def __init__(self, port_path):
        self.cap = cv2.VideoCapture(port_path)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, frame[display][0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, frame[display][1])
        self.cap.set(3, 1)
        
    def take_picture(self, path):
        ret = self.cap.grab()  # Grab one frame to reduce latency
        ret, frame = self.cap.read()
        if ret:
            cv2.imwrite(path, frame)

    def release(self):
        self.cap.release()

class PiCamera:
    def __init__(self):
        self.cap = Picamera2()
        self.cap.configure(
            self.cap.create_still_configuration(main={"size": (frame[display][0], frame[display][1])})
        )
        self.cap.set_controls({"AfMode": 2})
        self.cap.start()

    def take_picture(self, path):
        # frame = self.cap.capture_array()
        # cv2.imwrite(path, frame)
        self.cap.capture_file(path)

    def release(self):
        self.cap.stop()
