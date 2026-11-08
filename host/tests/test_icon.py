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
                alpha = frame.getchannel("A")
                self.assertLessEqual(alpha.getpixel((0, 0)), 2)
                self.assertEqual(alpha.getpixel((size // 2, size // 2)), 255)
                self.assertTrue(any(0 < value < 255 for value in alpha.getdata()),
                                f"{size}px icon should have smooth edges")

    def test_large_icon_is_available_for_window_preview(self):
        with Image.open(ASSETS / "coaster.png") as icon:
            self.assertEqual(icon.size, (256, 256))
