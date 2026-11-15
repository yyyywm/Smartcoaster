"""Local SQLite persistence for settings, reminders, and drink events."""
from __future__ import annotations

import csv
from calendar import monthrange
from datetime import date, datetime
import json
import os
from pathlib import Path
import sqlite3

from .model import Settings


def default_database_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", "")) if os.environ.get("LOCALAPPDATA") else Path.home() / ".local" / "share"
    return base / "SmartCoaster" / "coaster.db"


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS drinks (
            id INTEGER PRIMARY KEY, at TEXT NOT NULL, day TEXT NOT NULL,
            ml REAL NOT NULL, estimated INTEGER NOT NULL)""")
        self.conn.execute("CREATE INDEX IF NOT EXISTS drinks_day ON drinks(day)")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _get(self, key: str):
        row = self.conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def _put(self, key: str, value) -> None:
        self.conn.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                          (key, json.dumps(value)))
        self.conn.commit()

    def load_settings(self) -> Settings:
        saved = self._get("settings")
        return Settings.from_dict(saved) if saved else Settings()

    def save_settings(self, settings: Settings) -> None:
        self._put("settings", settings.to_dict())

    def load_runtime(self) -> tuple[datetime | None, datetime | None, float]:
        data = self._get("runtime") or {}
        def timestamp(key):
            return datetime.fromisoformat(data[key]) if data.get(key) else None
        return timestamp("last_qualified"), timestamp("alert_started"), float(data.get("alert_progress_ml", 0))

    def save_runtime(self, last_qualified: datetime | None,
                     alert_started: datetime | None, progress_ml: float) -> None:
        self._put("runtime", {
            "last_qualified": last_qualified.isoformat() if last_qualified else None,
            "alert_started": alert_started.isoformat() if alert_started else None,
            "alert_progress_ml": progress_ml,
        })

    def add_drink(self, at: datetime, ml: float, estimated: bool) -> None:
        self.conn.execute("INSERT INTO drinks(at,day,ml,estimated) VALUES(?,?,?,?)",
                          (at.isoformat(), at.date().isoformat(), ml, int(estimated)))
        self.conn.commit()

    def list_drinks(self, limit: int = 200, offset: int = 0) -> list[tuple[int, str, float, bool]]:
        rows = self.conn.execute(
            "SELECT id,at,ml,estimated FROM drinks ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset)).fetchall()
        return [(int(id_), at, float(ml), bool(estimated))
                for id_, at, ml, estimated in rows]

    def delete_drinks(self, ids: list[int]) -> int:
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        cursor = self.conn.execute(f"DELETE FROM drinks WHERE id IN ({placeholders})", ids)
        self.conn.commit()
        return cursor.rowcount

    def clear_drinks(self, day: str | None = None) -> int:
        if day is None:
            cursor = self.conn.execute("DELETE FROM drinks")
        else:
            cursor = self.conn.execute("DELETE FROM drinks WHERE day=?", (day,))
        self.conn.commit()
        return cursor.rowcount

    def export_csv(self, path: Path) -> int:
        rows = self.conn.execute(
            "SELECT id,at,day,ml,estimated FROM drinks ORDER BY id").fetchall()
        with path.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(("id", "at", "day", "ml", "estimated"))
            writer.writerows(rows)
        return len(rows)

    def today_totals(self, now: datetime) -> tuple[float, float]:
        rows = self.conn.execute(
            "SELECT estimated, COALESCE(SUM(ml),0) FROM drinks WHERE day=? GROUP BY estimated",
            (now.date().isoformat(),)).fetchall()
        totals = {estimated: ml for estimated, ml in rows}
        return float(totals.get(0, 0)), float(totals.get(1, 0))

    def month_totals(self, year: int, month: int) -> dict[date, float]:
        """Confirmed drinking by saved local day, without pagination limits."""
        first = date(year, month, 1)
        last = date(year, month, monthrange(year, month)[1])
        rows = self.conn.execute(
            "SELECT day, SUM(ml) FROM drinks "
            "WHERE day>=? AND day<=? AND estimated=0 GROUP BY day",
            (first.isoformat(), last.isoformat())).fetchall()
        return {date.fromisoformat(day): float(ml) for day, ml in rows}

    def recent(self, limit: int = 8) -> list[tuple[str, float, bool]]:
        rows = self.conn.execute("SELECT at,ml,estimated FROM drinks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [(at, float(ml), bool(estimated)) for at, ml, estimated in rows]
