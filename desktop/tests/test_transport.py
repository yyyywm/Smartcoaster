import queue
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from coaster_app.transport import SerialFeed, available_ports


class FakePort:
    def __init__(self):
        self.writes = []
        self.written = threading.Event()
        self.write_at = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def write(self, data):
        self.writes.append(data)
        self.write_at = time.monotonic()
        self.written.set()

    def read_until(self, *_args):
        time.sleep(0.01)
        return b'{"status":{"weight_g":350,"state":"stable"}}\n'


class TransportTests(unittest.TestCase):
    def test_calibration_command_is_written_as_json_line(self):
        port = FakePort()
        messages = queue.Queue()
        with patch("serial.Serial", return_value=port):
            feed = SerialFeed("COM7", messages)
            feed.send_command({"cmd": "set_cup_calibration", "empty_g": 120, "full_g": 620})
            started = time.monotonic()
            feed.start()
            try:
                self.assertTrue(port.written.wait(2.5))
                self.assertGreaterEqual(port.write_at - started, 0.8)
                self.assertEqual(port.writes[0],
                                 b'{"cmd":"set_cup_calibration","empty_g":120,"full_g":620}\n')
            finally:
                feed.stop()

    def test_port_list_prioritizes_readable_device_names(self):
        ports = [SimpleNamespace(device="COM18", description="USB Serial Device (COM18)",
                                 vid=0x303A, pid=0x1001),
                 SimpleNamespace(device="COM4", description="Other (COM4)", vid=None, pid=None)]
        with patch("serial.tools.list_ports.comports", return_value=ports):
            self.assertEqual(available_ports(), [("COM4", "Other"),
                                                 ("COM18", "ESP32-C3 USB")])
