from pathlib import Path
import tempfile
import unittest

from PIL import Image

from coaster_app.reminder_image import import_picture, load_picture, render_picture


class ReminderImageTests(unittest.TestCase):
    def test_small_image_is_centered_without_upscaling(self):
        picture = Image.new("RGB", (40, 20), (200, 0, 0))
        rendered = render_picture(picture, (200, 100), "smart")
        self.assertEqual(rendered.size, (200, 100))
        self.assertEqual(rendered.getpixel((100, 50)), (160, 0, 0))
        self.assertNotEqual(rendered.getpixel((0, 0)), (160, 0, 0))

    def test_large_image_can_fill_or_show_whole_frame(self):
        picture = Image.new("RGB", (400, 200), (200, 20, 0))
        cover = render_picture(picture, (100, 100), "cover")
        contain = render_picture(picture, (100, 100), "contain")
        self.assertEqual(cover.size, (100, 100))
        self.assertEqual(contain.size, (100, 100))
        self.assertNotEqual(cover.getpixel((50, 0)), contain.getpixel((50, 0)))

    def test_import_survives_source_removal_and_rejects_invalid_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            Image.new("RGB", (64, 32), "blue").save(source)
            managed, size = import_picture(source, root / "data")
            source.unlink()
            self.assertEqual(size, (64, 32))
            self.assertEqual(load_picture(managed).size, (64, 32))
            invalid = root / "bad.png"
            invalid.write_text("not an image", encoding="utf-8")
            with self.assertRaises(ValueError):
                import_picture(invalid, root / "data")
