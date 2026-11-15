from datetime import date, datetime
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import Mock, patch

from coaster_app.calendar_view import ACHIEVED, EMPTY, MISSED
from coaster_app.storage import Store
from coaster_app.ui import App


class StatisticsStorageTests(unittest.TestCase):
    def test_month_groups_all_confirmed_records_by_saved_local_date(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coaster.db"
            store = Store(path)
            try:
                for _ in range(205):
                    store.add_drink(datetime.fromisoformat("2024-02-29T00:05:00+14:00"), 5, False)
                store.add_drink(datetime.fromisoformat("2024-02-29T12:00:00+08:00"), 500, True)
                store.add_drink(datetime(2024, 2, 28), 600, True)
                store.add_drink(datetime(2024, 1, 31), 900, False)
                store.add_drink(datetime(2024, 3, 1), 1200, False)
                expected = {date(2024, 2, 29): 1025.0}
                self.assertEqual(store.month_totals(2024, 2), expected)
                store.close()
                store = Store(path)
                self.assertEqual(store.month_totals(2024, 2), expected)
                store.clear_drinks("2024-02-29")
                self.assertEqual(store.month_totals(2024, 2), {})
                self.assertEqual(store.month_totals(2025, 2), {})
            finally:
                store.close()


class FixedDate(date):
    @classmethod
    def today(cls):
        return date(2026, 11, 15)


class StatisticsUITests(unittest.TestCase):
    def test_month_navigation_statuses_and_live_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "ui.db")
            store.add_drink(datetime(2026, 11, 1), 1000, False)
            store.add_drink(datetime(2026, 11, 2), 600, False)
            store.add_drink(datetime(2026, 11, 2), 900, True)
            store.add_drink(datetime(2026, 11, 3), 2000, True)
            store.add_drink(datetime(2026, 11, 16), 2000, False)
            feed = Mock()
            with patch("coaster_app.ui.available_ports", return_value=[]), patch("coaster_app.ui.date", FixedDate):
                app = App(store, feed, queue.Queue())
                try:
                    app.core.settings.daily_goal_ml = 1000
                    self.assertEqual(list(app.view_buttons), ["overview", "statistics", "settings", "records"])
                    app._show_view("statistics")
                    app.update_idletasks()
                    canvas = app.statistics_calendar

                    def item(day, part, attribute="text"):
                        return canvas.itemcget(f"day-2026-11-{day:02}-{part}", attribute)

                    self.assertEqual(item(1, "status"), "达标")
                    self.assertEqual(item(1, "amount", "fill"), ACHIEVED)
                    self.assertEqual(item(2, "status"), "未达标")
                    self.assertEqual(item(2, "amount", "fill"), MISSED)
                    self.assertEqual(item(2, "amount"), "600 ml")
                    self.assertEqual(item(3, "amount"), "无记录")
                    self.assertEqual(item(3, "amount", "fill"), EMPTY)
                    self.assertEqual(item(16, "amount"), "—")
                    self.assertFalse(canvas.find_withtag("day-2026-11-16-status"))
                    self.assertEqual(app.statistics_achieved_var.get(), "本月已达标 1 天")
                    # November starts on Sunday and occupies six complete calendar rows.
                    x1, y1 = canvas.coords("day-2026-11-01-number")
                    x2, y2 = canvas.coords("day-2026-11-02-number")
                    _, y30 = canvas.coords("day-2026-11-30-number")
                    self.assertGreater(x1, x2)
                    self.assertLess(y1, y2)
                    self.assertLess(y2, y30)
                    self.assertTrue(canvas.find_withtag("today"))

                    # New drinks update the open calendar; deleting and saving goals also refresh it.
                    app._handle_frame({"event": "drink", "ml": 1000, "estimated": 0}, datetime(2026, 11, 15))
                    app._render()
                    self.assertEqual(item(15, "status"), "达标")
                    self.assertEqual(app.statistics_achieved_var.get(), "本月已达标 2 天")
                    with patch.object(FixedDate, "today", return_value=date(2026, 11, 16)):
                        app._render()
                        self.assertEqual(item(16, "status"), "达标")
                        self.assertIn(canvas.find_withtag("today")[0],
                                      canvas.find_withtag("day-2026-11-16"))
                        self.assertEqual(app.statistics_achieved_var.get(), "本月已达标 3 天")
                    app._show_view("records")
                    app._clear_records("all")
                    app._clear_records("all")
                    app._show_view("statistics")
                    self.assertEqual(item(1, "amount"), "无记录")
                    store.add_drink(datetime(2026, 11, 1), 1000, False)
                    app._render()
                    app._show_view("settings")
                    app.entries["daily_goal_ml"].delete(0, "end")
                    app.entries["daily_goal_ml"].insert(0, "1500")
                    app._save_settings()
                    app._show_view("statistics")
                    self.assertEqual(item(1, "status"), "未达标")

                    app.statistics_month = date(2026, 12, 1)
                    app._change_statistics_month(1)
                    self.assertEqual(app.statistics_month_var.get(), "2027年1月")
                    app._change_statistics_month(-1)
                    self.assertEqual(app.statistics_month_var.get(), "2026年12月")
                    app.statistics_month = date(2024, 2, 1)
                    app._refresh_statistics()
                    self.assertTrue(canvas.find_withtag("day-2024-02-29-number"))
                    self.assertFalse(canvas.find_withtag("day-2024-02-30-number"))
                    app._statistics_this_month()
                    self.assertEqual(app.statistics_month_var.get(), "2026年11月")

                    app.statistics_month = date.min
                    app._refresh_statistics()
                    app._change_statistics_month(-1)
                    self.assertEqual(app.statistics_month, date.min)
                    app.statistics_month = date(9999, 12, 1)
                    app._refresh_statistics()
                    app._change_statistics_month(1)
                    self.assertEqual(app.statistics_month, date(9999, 12, 1))
                finally:
                    app._shutdown()


if __name__ == "__main__":
    unittest.main()
