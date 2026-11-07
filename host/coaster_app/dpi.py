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
