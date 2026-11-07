#!/usr/bin/env python3
"""Smart Coaster desktop entry point."""
from __future__ import annotations

import argparse
from pathlib import Path
import queue
import sys
import unittest

from coaster_app.storage import Store, default_database_path
from coaster_app.transport import DemoFeed, SerialFeed, available_ports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="智能杯垫桌面端")
    parser.add_argument("--port", default="auto", help="串口名，如 COM18；默认自动查找 ESP32-C3")
    parser.add_argument("--simulate", action="store_true", help="无硬件演示")
    parser.add_argument("--list", action="store_true", help="列出可用串口")
    parser.add_argument("--db", type=Path, default=default_database_path(), help="SQLite 数据库位置")
    parser.add_argument("--selftest", action="store_true", help="运行离线测试")
    args = parser.parse_args(argv)

    if args.selftest:
        tests = unittest.defaultTestLoader.discover(str(Path(__file__).parent / "tests"))
        return 0 if unittest.TextTestRunner(verbosity=2).run(tests).wasSuccessful() else 1

    if args.list:
        try:
            ports = available_ports()
        except ImportError:
            print("缺少 pyserial：pip install -r host/requirements.txt", file=sys.stderr)
            return 1
        for name, description in ports:
            print(f"{name}  {description}")
        return 0

    if not args.simulate:
        try:
            import serial  # noqa: F401
        except ImportError:
            print("缺少 pyserial：pip install -r host/requirements.txt", file=sys.stderr)
            return 1

    from coaster_app.ui import App

    messages: queue.Queue = queue.Queue()
    feed = DemoFeed(messages) if args.simulate else SerialFeed(args.port, messages)
    store = Store(args.db)
    app = None
    try:
        app = App(store, feed, messages)
        app.mainloop()
    finally:
        if app is not None and not app._closing:
            app._shutdown()
        elif app is None:
            store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
