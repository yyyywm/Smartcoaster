from datetime import datetime
from pathlib import Path
import queue
import tempfile
import tkinter as tk
import unittest

from coaster_app.storage import Store
from coaster_app.transport import DemoFeed
from coaster_app.ui import App


class ReminderWindowTests(unittest.TestCase):
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
