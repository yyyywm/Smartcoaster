"""Physical display bounds and exact positioning for reminder windows."""
from __future__ import annotations

import sys


def monitor_bounds() -> list[tuple[int, int, int, int]]:
    """Return Windows monitor rectangles, with the primary monitor first."""
    if sys.platform != "win32":
        return []

    import ctypes
    from ctypes import wintypes

    class Rect(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", Rect),
                    ("rcWork", Rect), ("dwFlags", wintypes.DWORD)]

    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
        ctypes.POINTER(Rect), wintypes.LPARAM)
    user32 = ctypes.windll.user32
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MonitorInfo)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.EnumDisplayMonitors.argtypes = [
        wintypes.HDC, ctypes.POINTER(Rect), callback_type, wintypes.LPARAM]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    found: list[tuple[bool, tuple[int, int, int, int]]] = []

    def collect(handle, _dc, _rect, _data):
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            rect = info.rcMonitor
            bounds = (rect.left, rect.top,
                      rect.right - rect.left, rect.bottom - rect.top)
            if bounds[2] > 0 and bounds[3] > 0:
                found.append((bool(info.dwFlags & 1), bounds))
        return True

    if not user32.EnumDisplayMonitors(None, None, callback_type(collect), 0):
        return []
    found.sort(key=lambda item: not item[0])
    return [bounds for _primary, bounds in found]


def position_window(window, bounds: tuple[int, int, int, int]) -> None:
    """Place a Tk toplevel at physical coordinates, including negative offsets."""
    x, y, width, height = bounds
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.SetWindowPos.restype = wintypes.BOOL
        if user32.SetWindowPos(window.winfo_id(), None, x, y, width, height,
                               0x0004 | 0x0010):  # NOZORDER | NOACTIVATE
            return
    window.geometry(f"{width}x{height}{x:+d}{y:+d}")
