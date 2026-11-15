# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / "smart_coaster.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "assets" / "coaster.png"), "assets"),
           (str(root / "assets" / "coaster.ico"), "assets")],
    hiddenimports=["pystray._win32", "serial.tools.list_ports_windows"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="SmartCoaster",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(root / "assets" / "coaster.ico"),
)
