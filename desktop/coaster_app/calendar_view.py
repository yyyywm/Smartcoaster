"""Resizable Monday-first calendar for confirmed daily drinking."""
from __future__ import annotations

import calendar
from datetime import date
import tkinter as tk


ACHIEVED = "#218B50"
MISSED = "#CB4C4C"
EMPTY = "#95A5AF"


class DrinkingCalendar(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, bg="#FFFFFF", highlightthickness=0,
                         width=1, height=1)
        self.month = date.today().replace(day=1)
        self.today = date.today()
        self.totals: dict[date, float] = {}
        self.goal = 2000
        self.bind("<Configure>", self._draw)

    def set_month(self, month: date, totals: dict[date, float], goal: int,
                  today: date) -> None:
        self.month, self.totals, self.goal, self.today = month, totals, goal, today
        self._draw()

    def _draw(self, _event=None) -> None:
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if width < 7 or height < 40:
            return
        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(
            self.month.year, self.month.month)
        header = 30
        cw, ch = (width - 1) / 7, (height - header - 1) / len(weeks)
        self.create_rectangle(0, 0, width, header, fill="#EFF4F6", outline="")
        for col, title in enumerate(("周一", "周二", "周三", "周四", "周五", "周六", "周日")):
            self.create_text((col + .5) * cw, header / 2, text=title,
                             fill="#687982", font=("Microsoft YaHei UI", 10))
        # Keep both text rows legible in the existing minimum window size.
        compact = ch < 62
        for row, week in enumerate(weeks):
            for col, day in enumerate(week):
                if not day:
                    continue
                current = self.month.replace(day=day)
                tag = f"day-{current.isoformat()}"
                x, y = col * cw, header + row * ch
                total = self.totals.get(current)
                future = current > self.today
                color = EMPTY if future or total is None else (
                    ACHIEVED if total >= self.goal else MISSED)
                if current == self.today:
                    self.create_rectangle(x+3, y+3, x+cw-3, y+ch-3,
                                          fill="#F4FAFC", outline="#1599B5",
                                          width=2, tags=(tag, "today"))
                self.create_text(x+10, y+5, text=str(day), anchor="nw", fill=color,
                                 font=("Microsoft YaHei UI", 10, "bold"),
                                 tags=(tag, f"{tag}-number"))
                if current == self.today:
                    self.create_text(x+39, y+6, text="今天", anchor="nw",
                                     fill="#087DA4", font=("Microsoft YaHei UI", 8),
                                     tags=(tag,))
                amount = "—" if future else "无记录" if total is None else f"{total:.0f} ml"
                self.create_text(x+10, y+ch-7, text=amount, anchor="sw", fill=color,
                                 font=("Microsoft YaHei UI", 9 if compact else 10),
                                 tags=(tag, f"{tag}-amount"))
                if not future and total is not None:
                    self.create_text(x+cw-9, y+ch-7,
                                     text="达标" if total >= self.goal else "未达标",
                                     anchor="se", fill=color,
                                     font=("Microsoft YaHei UI", 8),
                                     tags=(tag, f"{tag}-status"))
        for col in range(8):
            self.create_line(col*cw, header, col*cw, height-1, fill="#E5ECEF")
        for row in range(len(weeks)+1):
            y = header + row*ch
            self.create_line(0, y, width-1, y, fill="#E5ECEF")
