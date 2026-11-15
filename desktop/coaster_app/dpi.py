"""Enable native Windows rendering before the first Tk window is created."""
from __future__ import annotations

import sys


def enable_native_dpi() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    try:
        # Per-monitor v2 keeps text sharp when the window moves between monitors.
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def set_windows_app_id() -> None:
    """Give the desktop app its own taskbar identity instead of Python's."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        shell32 = ctypes.windll.shell32
        shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
        shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
        shell32.SetCurrentProcessExplicitAppUserModelID("SmartCoaster.Desktop")
    except (AttributeError, OSError):
        pass
