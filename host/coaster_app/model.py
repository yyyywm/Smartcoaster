"""Pure reminder rules and user settings."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
import math


def parse_clock(value: str) -> time:
    try:
        parsed = datetime.strptime(value, "%H:%M").time()
    except (TypeError, ValueError) as exc:
        raise ValueError("时间须为 HH:MM，例如 09:00") from exc
    return parsed


@dataclass
class Settings:
    work_start: str = "09:00"
    work_end: str = "18:00"
    interval_min: int = 45
    sip_target_ml: int = 150
    daily_goal_ml: int = 2000
    cup_capacity_ml: int = 500
    cup_tare_g: float | None = None
    cup_full_g: float | None = None

    def validate(self) -> None:
        if parse_clock(self.work_start) == parse_clock(self.work_end):
            raise ValueError("上下班时间不能相同")
        for key, low, high in (
            ("interval_min", 1, 240),
            ("sip_target_ml", 1, 1000),
            ("daily_goal_ml", 100, 10000),
            ("cup_capacity_ml", 50, 3000),
        ):
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{key} 须在 {low}–{high} 之间")
        if self.cup_tare_g is not None:
            if (not isinstance(self.cup_tare_g, (int, float))
                    or not math.isfinite(self.cup_tare_g)
                    or not 0 <= self.cup_tare_g <= 5000):
                raise ValueError("空杯重须在 0–5000 g 之间")
        if self.cup_full_g is not None:
            if (self.cup_tare_g is None or not isinstance(self.cup_full_g, (int, float))
                    or not math.isfinite(self.cup_full_g)
                    or not self.cup_tare_g + 50 <= self.cup_full_g <= 8000):
                raise ValueError("满杯重须比空杯重多至少 50 g，且不超过 8000 g")

    @property
    def calibrated_capacity_ml(self) -> float | None:
        if self.cup_tare_g is None or self.cup_full_g is None:
            return None
        return self.cup_full_g - self.cup_tare_g

    def to_dict(self) -> dict:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        settings = cls(**{key: data[key] for key in cls.__dataclass_fields__ if key in data})
        settings.validate()
        return settings


def active_shift(now: datetime, settings: Settings) -> tuple[datetime, datetime] | None:
    """Return the current work window, including shifts crossing midnight."""
    start_clock = parse_clock(settings.work_start)
    end_clock = parse_clock(settings.work_end)
    start = datetime.combine(now.date(), start_clock, now.tzinfo)
    end = datetime.combine(now.date(), end_clock, now.tzinfo)
    if end > start:
        return (start, end) if start <= now < end else None
    if now >= start:
        return start, end + timedelta(days=1)
    yesterday_start = start - timedelta(days=1)
    return (yesterday_start, end) if now < end else None


class HydrationCore:
    """A reminder stays active until enough confirmed water is drunk."""

    def __init__(self, settings: Settings, last_qualified: datetime | None = None,
                 alert_started: datetime | None = None, alert_progress_ml: float = 0.0):
        self.settings = settings
        self.last_qualified = last_qualified
        self.alert_started = alert_started
        self.alert_progress_ml = max(0.0, alert_progress_ml)
        self.session_started_at: datetime | None = None

    def begin_session(self, now: datetime) -> None:
        """Start or resume reminder timing after launch or setup."""
        self.alert_started = None
        self.alert_progress_ml = 0.0
        self.session_started_at = now

    @property
    def alert_active(self) -> bool:
        return self.alert_started is not None

    def due_at(self, now: datetime) -> datetime | None:
        shift = active_shift(now, self.settings)
        if shift is None:
            return None
        start, end = shift
        baseline = self.last_qualified if self.last_qualified and self.last_qualified >= start else start
        if self.session_started_at is not None and self.session_started_at > baseline:
            baseline = self.session_started_at
        due = baseline + timedelta(minutes=self.settings.interval_min)
        return due if due < end else None

    def tick(self, now: datetime, connected: bool) -> bool:
        """Activate only while a device is connected; return whether state changed."""
        if self.alert_active or not connected:
            return False
        due = self.due_at(now)
        if due is not None and now >= due:
            self.alert_started = now
            self.alert_progress_ml = 0.0
            return True
        return False

    def register_drink(self, now: datetime, amount_ml: float, estimated: bool) -> bool:
        """Return True when a pending reminder is satisfied."""
        if estimated or not math.isfinite(amount_ml) or amount_ml <= 0:
            return False
        if self.alert_active:
            self.alert_progress_ml += amount_ml
            if self.alert_progress_ml >= self.settings.sip_target_ml:
                self.alert_started = None
                self.alert_progress_ml = 0.0
                self.last_qualified = now
                return True
        elif amount_ml >= self.settings.sip_target_ml:
            self.last_qualified = now
        return False

    def water_ml(self, weight_g: float | None, state: str) -> float | None:
        if state != "stable" or weight_g is None or self.settings.cup_tare_g is None:
            return None
        if not math.isfinite(weight_g):
            return None
        return max(0.0, weight_g - self.settings.cup_tare_g)
