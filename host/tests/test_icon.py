from pathlib import Path
import unittest

from PIL import Image


ASSETS = Path(__file__).resolve().parents[1] / "assets"


class IconTests(unittest.TestCase):
    def test_windows_icon_has_crisp_taskbar_sizes(self):
        with Image.open(ASSETS / "coaster.ico") as icon:
            self.assertTrue({16, 20, 24, 32, 40, 48, 256}.issubset(
                {width for width, height in icon.info["sizes"] if width == height}))
            for size in (16, 20, 24, 32, 40):
                frame = icon.ico.getimage((size, size)).convert("RGBA")
                self.assertEqual(frame.size, (size, size))
                colors = frame.getcolors(maxcolors=256)
                self.assertIsNotNone(colors)
                self.assertLessEqual(len(colors), 6,
                                     f"{size}px icon should use pixel-aligned shapes")

    def test_large_icon_is_available_for_window_preview(self):
        with Image.open(ASSETS / "coaster.png") as icon:
            self.assertEqual(icon.size, (256, 256))
