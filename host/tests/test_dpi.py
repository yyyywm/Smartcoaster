"""Windows must render Tk at the monitor's native pixel density."""
import ctypes
import sys
import tkinter as tk
import unittest

from coaster_app import ui  # noqa: F401 - import follows the production UI path


@unittest.skipUnless(sys.platform == "win32", "Windows DPI check")
class DpiTests(unittest.TestCase):
    def test_process_is_dpi_aware_before_tk_window(self):
        window = tk.Tk()
        try:
            awareness = ctypes.c_int(-1)
            result = ctypes.windll.shcore.GetProcessDpiAwareness(None, ctypes.byref(awareness))
            self.assertEqual(result, 0)
            self.assertGreaterEqual(awareness.value, 1,
                                    "DPI-unaware Tk windows are bitmap-scaled and look blurry")
        finally:
            window.destroy()
