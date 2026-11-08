"""Windows tray lifecycle; callbacks only enqueue commands for the Tk thread."""
from __future__ import annotations

from pathlib import Path
import threading
from typing import Callable

from PIL import Image


class TrayIcon:
    def __init__(self, image_path: Path, post_action: Callable[[str], None]):
        self.image_path = image_path
        self.post_action = post_action
        self._icon = None

    def show(self) -> None:
        if self._icon is not None:
            return
        import pystray

        with Image.open(self.image_path) as source:
            image = source.convert("RGBA")
        menu = pystray.Menu(
            pystray.MenuItem("打开主界面", lambda _icon, _item: self.post_action("open"),
                             default=True),
            pystray.MenuItem("退出", lambda _icon, _item: self.post_action("quit")),
        )
        icon = pystray.Icon("SmartCoaster", image, "智能杯垫 · 提醒运行中", menu)
        ready = threading.Event()
        failures: list[Exception] = []

        def setup(running_icon):
            try:
                running_icon.visible = True
            except Exception as exc:
                failures.append(exc)
            finally:
                ready.set()

        def run():
            try:
                icon.run(setup=setup)
            except Exception as exc:
                failures.append(exc)
                ready.set()

        threading.Thread(target=run, name="smart-coaster-tray", daemon=True).start()
        if not ready.wait(2) or failures:
            icon.stop()
            raise RuntimeError("无法启动系统托盘图标") from (failures[0] if failures else None)
        self._icon = icon

    def hide(self) -> None:
        icon, self._icon = self._icon, None
        if icon is not None:
            icon.stop()
