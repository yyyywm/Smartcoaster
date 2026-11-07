from datetime import datetime, timedelta, timezone
from pathlib import Path
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


class ReminderTests(unittest.TestCase):
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
