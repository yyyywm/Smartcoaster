"""A compact, animated glass that only shows a calibrated water level."""
from __future__ import annotations

import time
import tkinter as tk


class WaterLevelView(tk.Canvas):
    def __init__(self, parent, *, surface: str, outline: str, water: str,
                 highlight: str, text: str):
        super().__init__(parent, width=228, height=300, bg=surface,
                         highlightthickness=0, borderwidth=0)
        self.surface = surface
        self.outline = outline
        self.water = water
        self.highlight = highlight
        self.text = text
        self.level = 0.0
        self.target: float | None = None
        self.placeholder = "尚未标定"
        self._animation_job: str | None = None
        self._animation_from = 0.0
        self._animation_at = 0.0
        self._draw()

    def set_reading(self, level: float | None, placeholder: str = "") -> None:
        self.placeholder = placeholder
        if level is None:
            self._cancel_animation()
            self.target = None
            self.level = 0.0
            self._draw()
            return
        level = max(0.0, min(1.0, level))
        if self.target is not None and abs(level - self.target) < 0.01:
            return
        self._cancel_animation()
        self.target = level
        self._animation_from = self.level
        self._animation_at = time.monotonic()
        self._animate()

    def _animate(self) -> None:
        self._animation_job = None
        if self.target is None:
            return
        progress = min(1.0, (time.monotonic() - self._animation_at) / 0.42)
        eased = 1.0 - (1.0 - progress) ** 3
        self.level = self._animation_from + (self.target - self._animation_from) * eased
        self._draw()
        if progress < 1.0:
            self._animation_job = self.after(16, self._animate)

    def _cancel_animation(self) -> None:
        if self._animation_job is not None:
            try:
                self.after_cancel(self._animation_job)
            except tk.TclError:
                pass
            self._animation_job = None

    def _draw(self) -> None:
        self.delete("all")
        top, bottom = 32, 258
        if self.target is not None and self.level > 0:
            waterline = bottom - self.level * (bottom - top)
            fraction = (waterline - top) / (bottom - top)
            left = 48 + 13 * fraction
            right = 180 - 13 * fraction
            middle = (left + right) / 2
            wave = min(3.0, 8.0 * self.level)
            self.create_polygon(
                left, waterline + wave,
                left + (middle - left) / 2, waterline - wave,
                middle, waterline + wave,
                middle + (right - middle) / 2, waterline - wave,
                right, waterline + wave,
                167, bottom - 3, 61, bottom - 3,
                fill=self.water, outline="")
            self.create_line(left, waterline + wave,
                             middle, waterline - wave / 2,
                             right, waterline + wave,
                             fill=self.highlight, width=2, smooth=True)
        self.create_line(42, top, 55, bottom, 173, bottom, 186, top,
                         fill=self.outline, width=4, joinstyle="round")
        self.create_line(39, top, 189, top, fill=self.outline, width=4,
                         capstyle="round")
        self.create_line(58, 50, 66, 218, fill=self.highlight,
                         width=2, capstyle="round")
        if self.target is None:
            self.create_text(114, 143, text=self.placeholder,
                             fill=self.text, font=("Microsoft YaHei UI", 11))
        self.create_text(114, 287,
                         text="实时水位" if self.target is not None else "杯子状态",
                         fill=self.text, font=("Microsoft YaHei UI", 9))

    def destroy(self) -> None:
        self._cancel_animation()
        super().destroy()
