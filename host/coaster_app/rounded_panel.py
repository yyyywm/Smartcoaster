"""Rounded card surface for Tk layouts that still use ordinary child widgets."""
from __future__ import annotations

import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from .soft_button import _corner_points, _rgb


class RoundedPanel(tk.Frame):
    def __init__(self, parent, *, surface: str, **kwargs):
        super().__init__(parent, bg=surface, highlightthickness=0, **kwargs)
        self._corner_images = []
        size, scale = 18, 3
        full = size * 2 * scale
        mask = Image.new("L", (full, full), 0)
        ImageDraw.Draw(mask).polygon(_corner_points(full, full, 0, 16 * scale), fill=255)
        background = Image.new("RGB", (full, full), _rgb(parent.cget("bg")))
        foreground = Image.new("RGB", (full, full), _rgb(surface))
        background.paste(foreground, (0, 0), mask)
        background = background.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
        for x, y, anchor, box in (
            (0, 0, "nw", (0, 0, size, size)),
            (1, 0, "ne", (size, 0, size * 2, size)),
            (0, 1, "sw", (0, size, size, size * 2)),
            (1, 1, "se", (size, size, size * 2, size * 2)),
        ):
            photo = ImageTk.PhotoImage(background.crop(box), master=self)
            corner = tk.Label(self, image=photo, bg=parent.cget("bg"), bd=0,
                              highlightthickness=0)
            corner.place(relx=x, rely=y, anchor=anchor)
            self._corner_images.append(photo)


class RoundedField(tk.Canvas):
    """Rounded entry background with a normal Tk Entry for editing and selection."""

    def __init__(self, parent, *, surface: str, foreground: str):
        super().__init__(parent, height=34, bg=parent.cget("bg"), bd=0,
                         highlightthickness=0)
        self._surface = surface
        self._focused = False
        self._photo = None
        self._backdrop = self.create_image(0, 0, anchor="nw")
        self.entry = tk.Entry(self, bg=surface, fg=foreground,
                              insertbackground=foreground, relief="flat",
                              highlightthickness=0, bd=0,
                              font=("Segoe UI Variable Text", 11))
        self._window = self.create_window(11, 7, window=self.entry, anchor="nw")
        self.bind("<Configure>", self._draw)
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)

    def _focus_in(self, _event):
        self._focused = True
        self._draw()

    def _focus_out(self, _event):
        self._focused = False
        self._draw()

    def _draw(self, _event=None):
        width, height = self.winfo_width(), self.winfo_height()
        if width < 24:
            return
        scale = 3
        image = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
        mask = Image.new("L", image.size, 0)
        ImageDraw.Draw(mask).polygon(_corner_points(*image.size, 1 * scale, 11 * scale), fill=255)
        fill = Image.new("RGB", image.size, _rgb(self._surface))
        image.paste(fill, (0, 0), mask)
        if self._focused:
            points = _corner_points(*image.size, 1 * scale, 11 * scale)
            ImageDraw.Draw(image).line(points + [points[0]], fill=(8, 125, 164, 190),
                                       width=2 * scale)
        self._photo = ImageTk.PhotoImage(image.resize((width, height), Image.Resampling.LANCZOS), master=self)
        self.itemconfigure(self._backdrop, image=self._photo)
        self.itemconfigure(self._window, width=max(12, width - 22), height=20)
