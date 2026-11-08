from datetime import datetime, timedelta
from pathlib import Path
import queue
import tempfile
import tkinter as tk
from tkinter import messagebox
import unittest
from unittest.mock import patch

from coaster_app.displays import monitor_bounds
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
        self.commands = []

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def send_command(self, command):
        self.commands.append(command)


class ReminderWindowTests(unittest.TestCase):
    def test_reminder_covers_every_monitor_and_dismisses_together(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            now = datetime.now().astimezone()
            messages = queue.Queue()
            app = App(store, DemoFeed(messages), messages)
            try:
                app.update()
                app.core.alert_started = now
                app.connection = True
                app.last_frame_at = now
                monitors = [(0, 0, 800, 600), (800, -100, 800, 600)]
                with patch("coaster_app.ui.monitor_bounds", return_value=monitors):
                    app._tick()
                self.assertEqual(len(app.alert_windows), 2)
                app.update()
                for window, (x, y, width, height) in zip(app.alert_windows, monitors):
                    self.assertEqual((window.winfo_rootx(), window.winfo_rooty(),
                                      window.winfo_width(), window.winfo_height()),
                                     (x, y, width, height))
                app.alert_windows[1].event_generate("<Escape>")
                self.assertEqual(app.alert_windows, [])
                self.assertIsNone(app.alert_window)
                self.assertFalse(app.core.alert_active)
                self.assertTrue(app.winfo_exists())
            finally:
                app._shutdown()

    def test_leaving_settings_does_not_skip_an_overdue_reminder(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            now = datetime.now().astimezone()
            store.save_settings(Settings(
                work_start=(now - timedelta(hours=1)).strftime("%H:%M"),
                work_end=(now + timedelta(hours=1)).strftime("%H:%M"),
                interval_min=5,
            ))
            messages = queue.Queue()
            feed = FakeSerialFeed("COM18", messages)
            with patch("coaster_app.ui.available_ports", return_value=[]):
                app = App(store, feed, messages)
            try:
                app.connection = True
                app.last_frame_at = now
                app.core.session_started_at = now - timedelta(minutes=6)
                app._show_view("settings")
                app._tick()
                self.assertFalse(app.core.alert_active)
                with patch.object(app, "_show_alert") as show_alert:
                    app._show_view("overview")
                    app._tick()
                    self.assertTrue(app.core.alert_active)
                    show_alert.assert_called_once()
            finally:
                app._shutdown()

    def test_empty_pad_zero_recovers_false_cup_and_clears_cup_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            store.save_settings(Settings(cup_tare_g=120, cup_full_g=620))
            messages = queue.Queue()
            feed = FakeSerialFeed("COM18", messages)
            with patch("coaster_app.ui.available_ports", return_value=[]):
                app = App(store, feed, messages)
            try:
                now = datetime.now().astimezone()
                app.connection = True
                app.last_frame_at = now
                app.device_state = "stable"
                app.weight_g = 90.5
                app._zero_pad()
                self.assertEqual(feed.commands, [])
                app._zero_pad()
                self.assertEqual(feed.commands, [{"cmd": "calibrate_empty"}])
                app._handle_frame({"ack": "calibrate_empty", "ok": 1}, now)
                self.assertIsNone(app.core.settings.cup_tare_g)
                self.assertIsNone(store.load_settings().cup_full_g)
                self.assertIsNone(app.weight_g)
                self.assertEqual(app.device_state, "unknown")
            finally:
                app.update_idletasks()
                app._shutdown()

    def test_offline_pending_alert_does_not_block_app_close(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            messages = queue.Queue()
            feed = FakeSerialFeed("COM7", messages)
            with patch("coaster_app.ui.available_ports", return_value=[]):
                app = App(store, feed, messages)
            try:
                app.core.alert_started = datetime.now().astimezone()
                app._on_close()
                self.assertTrue(app._closing)
                self.assertIsNone(app.alert_window)
            finally:
                app._shutdown()

    def test_device_disconnect_releases_fullscreen_until_reconnected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            messages = queue.Queue()
            feed = FakeSerialFeed("COM7", messages)
            with patch("coaster_app.ui.available_ports", return_value=[]):
                app = App(store, feed, messages)
            try:
                now = datetime.now().astimezone()
                app.connection = True
                app.last_frame_at = now
                app.core.alert_started = now
                app._tick()
                self.assertIsNotNone(app.alert_window)
                app.connection = False
                app.last_frame_at = None
                app._tick()
                self.assertIsNone(app.alert_window)
                self.assertTrue(app.core.alert_active)
                app.connection = True
                app.last_frame_at = datetime.now().astimezone()
                app._tick()
                self.assertIsNotNone(app.alert_window)
            finally:
                app.update_idletasks()
                app._shutdown()

    def test_launch_with_saved_alert_auto_monitors_and_allows_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            now = datetime.now().astimezone()
            store.save_settings(Settings(work_start=(now - timedelta(hours=1)).strftime("%H:%M"),
                                         work_end=(now + timedelta(hours=1)).strftime("%H:%M"),
                                         interval_min=5))
            yesterday = now - timedelta(days=1)
            store.save_runtime(None, yesterday, 0)
            store.add_drink(yesterday, 120, False)
            messages = queue.Queue()
            app = App(store, DemoFeed(messages), messages)
            try:
                app.update()
                app._tick()
                self.assertIsNone(app.alert_window)
                self.assertFalse(app.core.alert_active)
                self.assertIsNotNone(app.core.session_started_at)
                self.assertIsNone(store.load_runtime()[1])
                self.assertEqual(store.list_drinks()[0][2], 120)
                app._show_view("settings")
                app.core.session_started_at = now - timedelta(minutes=20)
                app.connection = True
                app.last_frame_at = datetime.now().astimezone()
                app._tick()
                self.assertIsNone(app.alert_window)
                app.entries["interval_min"].delete(0, tk.END)
                app.entries["interval_min"].insert(0, "30")
                app._save_settings()
                self.assertEqual(app.core.settings.interval_min, 30)
                app._show_view("overview")
                app._tick()
                self.assertIsNone(app.alert_window)
                self.assertGreater(app.core.due_at(datetime.now().astimezone()),
                                   datetime.now().astimezone())
                app.core.session_started_at -= timedelta(minutes=11)
                app.last_frame_at = datetime.now().astimezone()
                app._tick()
                self.assertIsNotNone(app.alert_window)
            finally:
                app._shutdown()

    def test_device_calibration_is_loaded_when_local_settings_have_none(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            messages = queue.Queue()
            feed = FakeSerialFeed("COM7", messages)
            with patch("coaster_app.ui.available_ports", return_value=[("COM7", "ESP32-C3")]):
                app = App(store, feed, messages)
            try:
                messages.put(("connection", True, "COM7"))
                app._consume_messages(datetime.now().astimezone())
                self.assertEqual(feed.commands[-1], {"cmd": "get_config"})
                app._handle_frame({"config": {"empty_cup_g": 120.0,
                                               "full_cup_g": 620.0}}, datetime.now().astimezone())
                self.assertEqual(store.load_settings().calibrated_capacity_ml, 500)
                self.assertEqual(app.core.settings.cup_tare_g, 120)
            finally:
                app.update_idletasks()
                app._shutdown()

    def test_empty_and_full_calibration_sync_to_device(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            messages = queue.Queue()
            feed = FakeSerialFeed("COM7", messages)
            with patch("coaster_app.ui.available_ports", return_value=[("COM7", "ESP32-C3")]):
                app = App(store, feed, messages)
            try:
                now = datetime.now().astimezone()
                app.connection = True
                app.last_frame_at = now
                app.device_state = "stable"
                app.weight_g = 120.0
                app._calibrate_cup()
                app._calibrate_cup()
                self.assertEqual(feed.commands[-1],
                                 {"cmd": "set_cup_calibration", "empty_g": 120.0, "full_g": 0})
                app.weight_g = 620.0
                app._calibrate_full()
                app._calibrate_full()
                self.assertEqual(feed.commands[-1],
                                 {"cmd": "set_cup_calibration", "empty_g": 120.0, "full_g": 620.0})
                self.assertEqual(app.core.settings.calibrated_capacity_ml, 500)
                self.assertEqual(store.load_settings().cup_full_g, 620)
                app._handle_frame({"ack": "set_cup_calibration", "ok": 0}, now)
                app._render()
                self.assertIn("标定未同步", app.conn_var.get())
                app._handle_frame({"ack": "set_cup_calibration", "ok": 1}, now)
                app._render()
                self.assertNotIn("标定未同步", app.conn_var.get())
            finally:
                app.update_idletasks()
                app._shutdown()

    def test_data_view_requires_second_click_before_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            now = datetime.now().astimezone()
            store.add_drink(now, 100, False)
            store.add_drink(now, 50, False)
            messages = queue.Queue()
            app = App(store, DemoFeed(messages), messages)
            try:
                app._show_view("records")
                export_path = Path(directory) / "drinks.csv"
                with patch("coaster_app.ui.filedialog.asksaveasfilename",
                           return_value=str(export_path)):
                    app._export_records()
                self.assertIn("100", export_path.read_text(encoding="utf-8-sig"))
                selected = app.records_tree.get_children()[0]
                app.records_tree.selection_set(selected)
                app._delete_selected()
                self.assertEqual(store.today_totals(now), (150, 0))
                app._delete_selected()
                self.assertEqual(store.today_totals(now), (100, 0))
                app._clear_records("all")
                self.assertEqual(store.today_totals(now), (100, 0))
                app._clear_records("all")
                self.assertEqual(store.today_totals(now), (0, 0))
            finally:
                app.update_idletasks()
                app._shutdown()

    def test_dashboard_fits_without_scroll_at_minimum_window_size(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            for _ in range(20):
                store.add_drink(datetime.now().astimezone(), 120, False)
            messages = queue.Queue()
            feed = FakeSerialFeed("auto", messages)
            with patch("coaster_app.ui.available_ports", return_value=[]):
                try:
                    app = App(store, feed, messages)
                except tk.TclError:
                    store.close()
                    self.skipTest("图形桌面不可用")
                try:
                    app.update_idletasks()
                    self.assertAlmostEqual(app.winfo_width() / app.winfo_height(),
                                           (1 + 5 ** 0.5) / 2, delta=0.01)
                    app.geometry("960x593")
                    def descendants(widget):
                        for child in widget.winfo_children():
                            yield child
                            yield from descendants(child)

                    for view in ("overview", "settings", "records"):
                        with self.subTest(view=view):
                            app._show_view(view)
                            app._render()
                            app._set_action_status("请先把空杯放在杯垫上，等待重量稳定。", error=True)
                            app.update()
                            widgets = list(descendants(app))
                            self.assertFalse(any(isinstance(widget, tk.Scrollbar) for widget in widgets))
                            left = app.winfo_rootx()
                            top = app.winfo_rooty()
                            right = left + app.winfo_width()
                            bottom = top + app.winfo_height()
                            for widget in widgets:
                                if widget.winfo_ismapped():
                                    self.assertGreaterEqual(widget.winfo_rootx(), left,
                                                            f"控件超出窗口：{widget}")
                                    self.assertGreaterEqual(widget.winfo_rooty(), top,
                                                            f"控件超出窗口：{widget}")
                                    self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), right,
                                                         f"控件超出窗口：{widget}")
                                    self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom,
                                                         f"控件超出窗口：{widget}")
                finally:
                    app.update_idletasks()
                    app._shutdown()

    def test_settings_actions_return_with_inline_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            messages = queue.Queue()
            try:
                app = App(store, DemoFeed(messages), messages)
            except tk.TclError:
                store.close()
                self.skipTest("图形桌面不可用")
            try:
                with patch.object(messagebox, "showinfo", side_effect=AssertionError("模态提示阻塞界面")), \
                     patch.object(messagebox, "showwarning", side_effect=AssertionError("模态警告阻塞界面")), \
                     patch.object(messagebox, "askyesno", side_effect=AssertionError("模态确认阻塞界面")):
                    app._save_settings()
                    self.assertIn("已保存", app.action_status.get())
                    app._calibrate_cup()
                    self.assertIn("等待重量稳定", app.action_status.get())
                    now = datetime.now().astimezone()
                    app.connection = True
                    app.last_frame_at = now
                    app.device_state = "stable"
                    app.weight_g = 120.0
                    app._calibrate_cup()
                    self.assertIsNone(app.core.settings.cup_tare_g)
                    app.weight_g = 125.0
                    app._calibrate_cup()
                    self.assertIsNone(app.core.settings.cup_tare_g)
                    app._calibrate_cup()
                    self.assertEqual(app.core.settings.cup_tare_g, 125.0)
            finally:
                app._shutdown()

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
                    app._toggle_connection()
                    self.assertIsNone(app.feed)
                    self.assertEqual(app.connect_button.cget("text"), "连接设备")
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

    def test_reminder_can_be_dismissed_without_closing_app_or_recording_drink(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            now = datetime.now().astimezone()
            messages = queue.Queue()
            try:
                app = App(store, DemoFeed(messages), messages)
            except tk.TclError:
                store.close()
                self.skipTest("图形桌面不可用")
            try:
                app.update()
                app.core.alert_started = now
                app._tick()
                self.assertIsNotNone(app.alert_window)
                self.assertTrue(app.alert_window.overrideredirect())
                self.assertEqual(len(app.alert_windows), len(monitor_bounds()) or 1)
                if monitor_bounds():
                    app.update()
                    for window, rect in zip(app.alert_windows, monitor_bounds()):
                        self.assertEqual((window.winfo_rootx(), window.winfo_rooty(),
                                          window.winfo_width(), window.winfo_height()), rect)
                self.assertIn("5 分钟", app.dismiss_button.cget("text"))
                callback = app.tk.call("wm", "protocol", app.alert_window._w,
                                       "WM_DELETE_WINDOW")
                app.tk.call(callback)
                self.assertTrue(app.winfo_exists())
                self.assertIsNone(app.alert_window)
                self.assertFalse(app.core.alert_active)
                self.assertEqual(store.today_totals(now), (0, 0))
                app._tick()
                self.assertIsNone(app.alert_window)
                app.core.alert_started = now
                app._tick()
                app.update()
                app.alert_window.event_generate("<Escape>")
                self.assertIsNone(app.alert_window)
                self.assertTrue(app.winfo_exists())
                app.core.alert_started = now
                app._tick()
                app.update()
                app.alert_window.event_generate("<Control-Shift-Q>")
                self.assertIsNone(app.alert_window)
                self.assertTrue(app.winfo_exists())
                app.core.alert_started = now
                app._tick()
                app._handle_frame({"event": "drink", "ml": 200, "estimated": 1}, now)
                self.assertTrue(app.core.alert_active)
                app._handle_frame({"event": "drink", "ml": 80, "estimated": 0}, now)
                self.assertTrue(app.core.alert_active)
                app._handle_frame({"event": "drink", "ml": 70, "estimated": 0}, now)
                self.assertFalse(app.core.alert_active)
                self.assertIsNone(app.alert_window)
                self.assertEqual(store.today_totals(now), (150, 200))
            finally:
                app.update()
                app._shutdown()
