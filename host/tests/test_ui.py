from datetime import datetime
from pathlib import Path
import queue
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from coaster_app.model import Settings
from coaster_app.storage import Store
from coaster_app.transport import DemoFeed
from coaster_app.ui import App


class FakeSerialFeed:
    def __init__(self, requested_port, messages):
        self.requested_port = requested_port
        self.messages = messages
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class ReminderWindowTests(unittest.TestCase):
    def test_device_selection_refresh_connect_and_disconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            messages = queue.Queue()
            initial = FakeSerialFeed("auto", messages)
            with patch("coaster_app.ui.available_ports", return_value=[("COM7", "ESP32-C3")]) as ports, \
                 patch("coaster_app.ui.SerialFeed", side_effect=FakeSerialFeed):
                try:
                    app = App(store, initial, messages)
                except tk.TclError:
                    store.close()
                    self.skipTest("图形桌面不可用")
                try:
                    self.assertTrue(initial.started)
                    self.assertIn("COM7", " ".join(app.port_combo["values"]))
                    app.port_var.set(next(label for label in app.port_choices if label.startswith("COM7")))
                    app._connect_selected()
                    self.assertTrue(initial.stopped)
                    first = app.feed
                    self.assertEqual(first.requested_port, "COM7")
                    self.assertTrue(first.started)

                    ports.return_value = [("COM12", "ESP32-C3")]
                    app._refresh_ports()
                    self.assertIn("COM12", " ".join(app.port_combo["values"]))
                    app.port_var.set(next(label for label in app.port_choices if label.startswith("COM12")))
                    app._connect_selected()
                    self.assertTrue(first.stopped)
                    self.assertEqual(app.feed.requested_port, "COM12")

                    second = app.feed
                    app._disconnect()
                    self.assertTrue(second.stopped)
                    self.assertIsNone(app.feed)
                    self.assertEqual(app.connection_detail, "已断开")
                    app.port_var.set("自动查找 ESP32-C3")
                    app._connect_selected()
                    self.assertEqual(app.feed.requested_port, "auto")
                finally:
                    app.update_idletasks()
                    app._shutdown()

    def test_cup_is_visible_before_empty_cup_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            store.save_settings(Settings(work_start="02:00", work_end="03:00"))
            messages = queue.Queue()
            app = App(store, DemoFeed(messages), messages)
            try:
                app.update()
                now = datetime.now().astimezone()
                app.connection = True
                app.connection_detail = "COM18"
                app._handle_frame({"status": {"weight_g": 665.4, "state": "stable"}}, now)
                app._render()
                self.assertEqual(app.water_var.get(), "665.4 g")
                self.assertIn("空杯重", app.water_note.get())
            finally:
                app._shutdown()

    def test_fullscreen_reminder_requires_confirmed_drink(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            now = datetime.now().astimezone()
            store.save_runtime(None, now, 0)
            messages = queue.Queue()
            try:
                app = App(store, DemoFeed(messages), messages)
            except tk.TclError:
                store.close()
                self.skipTest("图形桌面不可用")
            try:
                app.update()
                app._tick()
                self.assertIsNotNone(app.alert_window)
                self.assertTrue(app.alert_window.attributes("-fullscreen"))
                app._on_close()
                self.assertTrue(app.winfo_exists())
                app._handle_frame({"event": "drink", "ml": 200, "estimated": 1}, now)
                self.assertTrue(app.core.alert_active)
                app._handle_frame({"event": "drink", "ml": 80, "estimated": 0}, now)
                self.assertTrue(app.core.alert_active)
                app._handle_frame({"event": "drink", "ml": 70, "estimated": 0}, now)
                self.assertFalse(app.core.alert_active)
                self.assertIsNone(app.alert_window)
                self.assertEqual(store.today_totals(now), (150, 200))
                app.geometry("1100x600")
                app.update()
                viewport = next(child for child in app.winfo_children()
                                if child.winfo_class() == "Canvas")
                content_height = int(viewport.cget("scrollregion").split()[-1])
                self.assertGreater(content_height, viewport.winfo_height())
                viewport.yview_moveto(1.0)
                self.assertAlmostEqual(viewport.yview()[1], 1.0)
            finally:
                app._shutdown()
