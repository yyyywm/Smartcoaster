from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from coaster_app.model import HydrationCore, Settings, active_shift
from coaster_app.storage import Store


TZ = timezone(timedelta(hours=8))


def at(hour: int, minute: int = 0, day: int = 7) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TZ)


class SettingsTests(unittest.TestCase):
    def test_rejects_invalid_interval_and_clock(self):
        with self.assertRaises(ValueError):
            Settings(interval_min=0).validate()
        with self.assertRaises(ValueError):
            Settings(work_start="25:00").validate()

    def test_overnight_shift(self):
        settings = Settings(work_start="22:00", work_end="06:00")
        self.assertEqual(active_shift(at(1, 0), settings)[0], at(22, 0, day=6))
        self.assertIsNone(active_shift(at(12, 0), settings))

    def test_water_requires_tare_and_stable_cup(self):
        core = HydrationCore(Settings())
        self.assertIsNone(core.water_ml(350, "stable"))
        core.settings.cup_tare_g = 120
        self.assertEqual(core.water_ml(350, "stable"), 230)
        self.assertEqual(core.water_ml(80, "stable"), 0)
        self.assertIsNone(core.water_ml(350, "no_cup"))

    def test_dynamic_level_requires_empty_and_full_calibration(self):
        core = HydrationCore(Settings(cup_tare_g=120))
        self.assertIsNone(core.calibrated_level(370, "stable"))
        core.settings.cup_full_g = 620
        self.assertEqual(core.calibrated_level(370, "stable"), 0.5)
        self.assertEqual(core.calibrated_level(80, "stable"), 0.0)
        self.assertEqual(core.calibrated_level(700, "stable"), 1.0)
        self.assertIsNone(core.calibrated_level(370, "no_cup"))

    def test_full_cup_calibration_requires_empty_cup_and_sets_capacity(self):
        with self.assertRaises(ValueError):
            Settings(cup_full_g=620).validate()
        with self.assertRaises(ValueError):
            Settings(cup_tare_g=120, cup_full_g=150).validate()
        settings = Settings(cup_tare_g=120, cup_full_g=620)
        settings.validate()
        self.assertEqual(settings.calibrated_capacity_ml, 500)
        self.assertEqual(Settings.from_dict(settings.to_dict()).cup_full_g, 620)

    def test_reminder_image_settings_round_trip_and_validate_mode(self):
        settings = Settings(reminder_image_path="C:/image.png",
                            reminder_image_name="image.png", reminder_image_mode="contain")
        self.assertEqual(Settings.from_dict(settings.to_dict()).reminder_image_mode,
                         "contain")
        with self.assertRaises(ValueError):
            Settings(reminder_image_mode="stretch").validate()


class ReminderTests(unittest.TestCase):
    def test_refill_resets_reminder_without_recording_water(self):
        core = HydrationCore(Settings(interval_min=45, sip_target_ml=150),
                             alert_started=at(10))
        self.assertTrue(core.register_refill(at(10, 2)))
        self.assertFalse(core.alert_active)
        self.assertIsNone(core.last_qualified)
        self.assertEqual(core.due_at(at(10, 2)), at(10, 47))
        self.assertFalse(core.tick(at(10, 46), True))
        self.assertTrue(core.tick(at(10, 47), True))

    def test_refill_before_reminder_or_during_snooze_starts_normal_interval(self):
        core = HydrationCore(Settings(interval_min=45))
        self.assertFalse(core.register_refill(at(9, 30)))
        self.assertEqual(core.due_at(at(9, 30)), at(10, 15))
        core.tick(at(10, 15), True)
        core.dismiss_alert(at(10, 16))
        self.assertFalse(core.register_refill(at(10, 17)))
        self.assertIsNone(core.snoozed_until)
        self.assertEqual(core.due_at(at(10, 17)), at(11, 2))

    def test_dismiss_alert_snoozes_without_claiming_a_drink(self):
        core = HydrationCore(Settings(interval_min=45), alert_started=at(10))
        self.assertTrue(core.dismiss_alert(at(10, 1)))
        self.assertFalse(core.alert_active)
        self.assertIsNone(core.last_qualified)
        self.assertEqual(core.due_at(at(10, 1)), at(10, 6))
        self.assertFalse(core.tick(at(10, 5), True))
        self.assertTrue(core.tick(at(10, 6), True))

    def test_short_interval_uses_half_interval_and_drink_cancels_snooze(self):
        core = HydrationCore(Settings(interval_min=5, sip_target_ml=150),
                             alert_started=at(10))
        core.dismiss_alert(at(10, 1))
        self.assertEqual(core.due_at(at(10, 1)), at(10, 3) + timedelta(seconds=30))
        core.register_drink(at(10, 2), 150, False)
        self.assertEqual(core.last_qualified, at(10, 2))
        self.assertEqual(core.due_at(at(10, 2)), at(10, 7))

    def test_snooze_past_work_end_waits_for_next_shift(self):
        core = HydrationCore(Settings(interval_min=45), alert_started=at(17, 55))
        core.dismiss_alert(at(17, 56))
        self.assertIsNone(core.due_at(at(17, 56)))
        self.assertFalse(core.tick(at(17, 59), True))
        self.assertEqual(core.due_at(at(9, 0) + timedelta(days=1)),
                         at(9, 45) + timedelta(days=1))

    def test_new_session_starts_interval_from_activation(self):
        core = HydrationCore(Settings(work_start="01:00", work_end="23:00",
                                      interval_min=5), alert_started=at(1, 26))
        core.begin_session(at(10))
        self.assertFalse(core.alert_active)
        self.assertEqual(core.due_at(at(10)), at(10, 5))
        self.assertFalse(core.tick(at(10, 4), True))
        self.assertTrue(core.tick(at(10, 5), True))

    def test_waits_for_work_time_and_device(self):
        core = HydrationCore(Settings(work_start="09:00", work_end="18:00",
                                      interval_min=45))
        self.assertFalse(core.tick(at(8, 59), True))
        self.assertFalse(core.tick(at(9, 45), False))
        self.assertTrue(core.tick(at(9, 45), True))

    def test_only_confirmed_drink_satisfies_alert(self):
        core = HydrationCore(Settings(interval_min=45, sip_target_ml=150))
        self.assertTrue(core.tick(at(10), True))
        self.assertFalse(core.register_drink(at(10, 1), 300, True))
        self.assertFalse(core.register_drink(at(10, 2), 70, False))
        self.assertTrue(core.alert_active)
        self.assertTrue(core.register_drink(at(10, 3), 80, False))
        self.assertFalse(core.alert_active)
        self.assertEqual(core.last_qualified, at(10, 3))
        self.assertFalse(core.tick(at(10, 47), True))
        self.assertTrue(core.tick(at(10, 48), True))

    def test_small_drink_before_alert_does_not_postpone_it(self):
        core = HydrationCore(Settings(interval_min=45, sip_target_ml=150))
        core.register_drink(at(9, 30), 10, False)
        self.assertTrue(core.tick(at(9, 45), True))


class StorageTests(unittest.TestCase):
    def test_manage_and_export_records_without_changing_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = Store(root / "coaster.db")
            store.save_settings(Settings(interval_min=30))
            store.add_drink(at(10), 100, False)
            store.add_drink(at(11), 40, True)
            store.add_drink(at(10, day=8), 50, False)
            rows = store.list_drinks()
            self.assertEqual([row[3] for row in rows], [False, True, False])
            self.assertEqual(store.export_csv(root / "records.csv"), 3)
            self.assertIn("estimated", (root / "records.csv").read_text(encoding="utf-8-sig"))
            self.assertEqual(store.delete_drinks([rows[1][0]]), 1)
            self.assertEqual(store.today_totals(at(12)), (100, 0))
            self.assertEqual(store.clear_drinks(at(12).date().isoformat()), 1)
            self.assertEqual(store.today_totals(at(12, day=8)), (50, 0))
            self.assertEqual(store.clear_drinks(), 1)
            self.assertEqual(store.load_settings().interval_min, 30)
            store.close()

    def test_existing_database_records_remain_manageable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.db"
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE drinks (id INTEGER PRIMARY KEY, at TEXT NOT NULL, "
                         "day TEXT NOT NULL, ml REAL NOT NULL, estimated INTEGER NOT NULL)")
            conn.execute("INSERT INTO drinks(at,day,ml,estimated) VALUES(?,?,?,?)",
                         (at(10).isoformat(), at(10).date().isoformat(), 100, 0))
            conn.commit()
            conn.close()
            store = Store(path)
            self.assertEqual(store.list_drinks()[0][2], 100)
            self.assertEqual(store.clear_drinks(), 1)
            store.close()

    def test_daily_lower_bound_and_runtime_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coaster.db"
            store = Store(path)
            settings = Settings(cup_tare_g=120)
            store.save_settings(settings)
            store.add_drink(at(10), 100, False)
            store.add_drink(at(11), 80, True)
            store.add_drink(at(10, day=8), 50, False)
            store.save_runtime(at(9), at(10), 30)
            store.close()

            reopened = Store(path)
            self.assertEqual(reopened.load_settings().cup_tare_g, 120)
            self.assertEqual(reopened.today_totals(at(12)), (100, 80))
            self.assertEqual(reopened.today_totals(at(12, day=8)), (50, 0))
            self.assertEqual(reopened.load_runtime(), (at(9), at(10), 30))
            reopened.close()


if __name__ == "__main__":
    unittest.main()
