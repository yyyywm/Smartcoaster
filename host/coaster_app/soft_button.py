"""A compact, keyboard-accessible button with continuous-curvature corners."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageTk


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))


def _mix(first: str, second: str, amount: float) -> str:
    a, b = _rgb(first), _rgb(second)
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))


def _corner_points(width: int, height: int, inset: int, radius: int) -> list[tuple[float, float]]:
    """Superellipse quarters give the edge and corner a continuous tangent."""
    left, top = inset, inset
    right, bottom = width - inset - 1, height - inset - 1
    r = min(radius, (bottom - top) / 2, (right - left) / 2)
    points = []
    corners = ((right - r, top + r, -math.pi / 2, 0),
               (right - r, bottom - r, 0, math.pi / 2),
               (left + r, bottom - r, math.pi / 2, math.pi),
               (left + r, top + r, math.pi, 3 * math.pi / 2))
    exponent = 2 / 4.2
    for cx, cy, start, end in corners:
        for step in range(17):
            angle = start + (end - start) * step / 16
            cosine, sine = math.cos(angle), math.sin(angle)
            points.append((cx + r * math.copysign(abs(cosine) ** exponent, cosine),
                           cy + r * math.copysign(abs(sine) ** exponent, sine)))
    return points


class SoftButton(tk.Canvas):
    """Drop-in for the small set of Button options used by the dashboard."""

    def __init__(self, parent, *, text: str, command=None, bg: str = "#E9F0F2",
                 fg: str = "#1D2B31", font=None, padx: int = 12, pady: int = 5,
                 state: str = "normal", **_unused):
        parent_color = parent.winfo_rgb(parent.cget("bg"))
        self._parent_bg = "#" + "".join(f"{channel // 256:02x}" for channel in parent_color)
        self._text = text
        self._command = command
        self._fill = bg
        self._foreground = fg
        self._font = font or ("Microsoft YaHei UI", 9)
        self._padx = max(8, padx)
        self._pady = max(4, pady)
        self._state = state
        self._hover = False
        self._pressed = False
        self._focused = False
        self._motion = 0.0
        self._animation = None
        self._photo = None
        self._image_item = None
        self._text_item = None
        self._font_obj = tkfont.Font(font=self._font)
        width, height = self._requested_size()
        super().__init__(parent, width=width, height=height, bg=self._parent_bg,
                         highlightthickness=0, borderwidth=0, relief="flat",
                         takefocus=True, cursor="hand2")
        self.bind("<Configure>", self._draw)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<FocusIn>", self._focus_in)
        self.bind("<FocusOut>", self._focus_out)
        self.bind("<KeyPress-space>", self._key_press)
        self.bind("<KeyRelease-space>", self._key_release)
        self.bind("<Return>", self._key_invoke)

    def _requested_size(self) -> tuple[int, int]:
        return (self._font_obj.measure(self._text) + self._padx * 2 + 8,
                self._font_obj.metrics("linespace") + self._pady * 2 + 8)

    def _draw(self, _event=None) -> None:
        width, height = self.winfo_width(), self.winfo_height()
        if width < 4 or height < 4:
            return
        scale = 3
        w, h = width * scale, height * scale
        disabled = self._state == "disabled"
        dark = sum(_rgb(self._fill)) < 390
        hover_color = _mix(self._fill, "#FFFFFF" if dark else "#BBCDD3",
                           0.16 if dark else 0.22)
        fill = _mix(self._fill, hover_color, self._motion)
        if self._pressed and not disabled:
            fill = _mix(fill, "#000000", 0.13)
        if disabled:
            fill = _mix(fill, self._parent_bg, 0.55)
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        mask = Image.new("L", (w, h), 0)
        path = _corner_points(w, h, 1 * scale, min(17 * scale, round(h * .43)))
        ImageDraw.Draw(mask).polygon(path, fill=255)
        top = _mix(fill, "#FFFFFF", 0.08 if dark else 0.24)
        bottom = _mix(fill, "#000000", 0.04 if dark else 0.025)
        pixels = Image.new("RGB", (1, h))
        for y in range(h):
            pixels.putpixel((0, y), _rgb(_mix(top, bottom, y / max(h - 1, 1))))
        canvas.paste(pixels.resize((w, h)), (0, 0))
        canvas.putalpha(mask)
        if self._focused and not disabled:
            ring = ImageDraw.Draw(canvas)
            ring_path = _corner_points(w, h, 1 * scale, min(19 * scale, round(h * .43)))
            ring.line(ring_path + [ring_path[0]],
                      fill=(35, 142, 180, 210), width=2 * scale, joint="curve")
        image = canvas.resize((width, height), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(image, master=self)
        if self._image_item is None:
            self._image_item = self.create_image(0, 0, image=self._photo, anchor="nw")
            self._text_item = self.create_text(width / 2, height / 2, text=self._text,
                                               font=self._font, fill=self._foreground)
        else:
            self.itemconfigure(self._image_item, image=self._photo)
            self.coords(self._text_item, width / 2, height / 2 + (1 if self._pressed else 0))
            self.itemconfigure(self._text_item, text=self._text, font=self._font,
                               fill=_mix(self._foreground, self._parent_bg, .4)
                               if disabled else self._foreground)

    def _animate(self, target: float) -> None:
        if self._animation is not None:
            self.after_cancel(self._animation)
            self._animation = None
        def step():
            self._motion += (target - self._motion) * .38
            if abs(target - self._motion) < .02:
                self._motion = target
                self._animation = None
            else:
                self._animation = self.after(16, step)
            self._draw()
        step()

    def _enter(self, _event):
        self._hover = True
        if self._state != "disabled":
            self._animate(1)

    def _leave(self, _event):
        self._hover = False
        self._pressed = False
        self._animate(0)

    def _press(self, _event):
        if self._state != "disabled":
            self.focus_set()
            self._pressed = True
            self._draw()

    def _release(self, event):
        was_pressed = self._pressed
        self._pressed = False
        self._draw()
        if was_pressed and self._state != "disabled" and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def _focus_in(self, _event):
        self._focused = True
        self._draw()

    def _focus_out(self, _event):
        self._focused = False
        self._pressed = False
        self._draw()

    def _key_press(self, _event):
        if self._state != "disabled":
            self._pressed = True
            self._draw()

    def _key_release(self, _event):
        if self._pressed:
            self._pressed = False
            self._draw()
            self.invoke()

    def _key_invoke(self, _event):
        self.invoke()

    def invoke(self):
        if self._state != "disabled" and self._command is not None:
            return self._command()
        return None

    def destroy(self):
        if self._animation is not None:
            self.after_cancel(self._animation)
            self._animation = None
        super().destroy()

    def configure(self, cnf=None, **kwargs):
        if cnf is None and not kwargs:
            return super().configure()
        options = dict(cnf or {}, **kwargs)
        if all(self.cget(key) == value for key, value in options.items()
               if key in {"text", "state", "bg", "fg", "command", "font"}) and not any(
                   key not in {"text", "state", "bg", "fg", "command", "font"} for key in options):
            return
        for key, attr in (("text", "_text"), ("state", "_state"),
                          ("bg", "_fill"), ("fg", "_foreground"),
                          ("command", "_command"), ("font", "_font")):
            if key in options:
                setattr(self, attr, options.pop(key))
        if "font" in kwargs or (cnf and "font" in cnf):
            self._font_obj = tkfont.Font(font=self._font)
        if options:
            super().configure(**options)
        if hasattr(self, "_font_obj"):
            width, height = self._requested_size()
            super().configure(width=width, height=height)
            self._draw()

    config = configure

    def cget(self, key):
        values = {"text": self._text, "state": self._state, "bg": self._fill,
                  "fg": self._foreground, "command": self._command, "font": self._font}
        return values[key] if key in values else super().cget(key)
