"""Serial and demo feeds. Worker threads never touch Tk or SQLite."""
from __future__ import annotations

import json
import queue
import re
import threading
import time


def available_ports() -> list[tuple[str, str]]:
    from serial.tools import list_ports
    ports = []
    for port in list_ports.comports():
        name = port.device
        description = (port.description or "串口设备").replace(f"({name})", "").strip()
        if port.vid == 0x303A and port.pid == 0x1001:
            description = "ESP32-C3 USB"
        ports.append((name, description[:42]))
    def sort_key(item: tuple[str, str]) -> tuple[str, int]:
        match = re.fullmatch(r"COM(\d+)", item[0], re.IGNORECASE)
        return ("COM", int(match.group(1))) if match else (item[0], 0)
    return sorted(ports, key=sort_key)


def choose_port(requested: str) -> str | None:
    if requested.lower() != "auto":
        return requested
    from serial.tools import list_ports
    for port in list_ports.comports():
        if port.vid == 0x303A and port.pid == 0x1001:
            return port.device
    return None


class SerialFeed:
    def __init__(self, requested_port: str, messages: queue.Queue):
        self.requested_port = requested_port
        self.messages = messages
        self.commands: queue.Queue[dict] = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="coaster-serial")

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)

    def send_command(self, command: dict) -> None:
        self.commands.put(command)

    def _run(self) -> None:
        import serial
        while not self.stop_event.is_set():
            port_name = choose_port(self.requested_port)
            if port_name is None:
                self.messages.put(("connection", False, "未发现 ESP32-C3 USB 串口"))
                self.stop_event.wait(2)
                continue
            try:
                with serial.Serial(port_name, 115200, timeout=0.5, write_timeout=0.5) as port:
                    self.messages.put(("connection", True, port_name))
                    last_frame = time.monotonic()
                    command_ready_at = last_frame + 1.0
                    while not self.stop_event.is_set():
                        if time.monotonic() >= command_ready_at:
                            while True:
                                try:
                                    command = self.commands.get_nowait()
                                except queue.Empty:
                                    break
                                port.write((json.dumps(command, separators=(",", ":")) + "\n").encode("utf-8"))
                        if time.monotonic() - last_frame > 10:
                            raise serial.SerialException("10 秒未收到设备数据")
                        data = port.read_until(b"\n", 512)
                        if not data.endswith(b"\n"):
                            continue
                        line = data.decode("utf-8", errors="replace").strip()
                        if not line.startswith("{"):
                            continue
                        try:
                            frame = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(frame, dict):
                            last_frame = time.monotonic()
                            self.messages.put(("frame", frame))
            except (serial.SerialException, OSError) as exc:
                self.messages.put(("connection", False, f"{port_name}: {exc}"))
                self.stop_event.wait(2)
            else:
                self.messages.put(("connection", False, "连接已关闭"))


class DemoFeed:
    def __init__(self, messages: queue.Queue):
        self.messages = messages
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="coaster-demo")
        self.weight_g = 380.0
        self.lock = threading.Lock()

    def start(self) -> None:
        self.messages.put(("connection", True, "演示模式"))
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)

    def simulate_drink(self, ml: float) -> None:
        with self.lock:
            self.weight_g = max(60.0, self.weight_g - ml)
            weight = self.weight_g
        self.messages.put(("frame", {"event": "drink", "ml": ml,
                                      "estimated": 0, "weight_g": weight}))

    def _run(self) -> None:
        while not self.stop_event.is_set():
            with self.lock:
                weight = self.weight_g
            self.messages.put(("frame", {"status": {"weight_g": weight,
                "state": "stable", "session_ml": 0, "since_drink_min": 0}}))
            self.stop_event.wait(1)
