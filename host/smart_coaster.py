#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能杯垫上位机（Smart Coaster Host）—— Tkinter 桌面版

用途：通过 USB 串口接收 ESP32-C3 杯垫固件发来的 JSON Lines，
      在桌面窗口实时显示重量/状态/喝水量/提醒，并可下发配置命令。

设计：
  - 只用 Python 标准库（tkinter / threading / queue / json），依赖极简：
      pip install pyserial
  - 串口读取放在后台线程，UI 只从主线程取数据，界面不卡顿
  - 无板子时用 --simulate 演示，复现完全相同的 JSON 行格式
  - --selftest 可在无桌面环境下自检协议解析与模拟数据

运行：
    python smart_coaster.py                    # 模拟器（推荐先这样试）
    python smart_coaster.py --port COM18       # 连真机
    python smart_coaster.py --list            # 列举可用串口
    python smart_coaster.py --selftest 12     # 无界面自检

协议详见项目根目录 README.md。
"""
from __future__ import annotations

import argparse
import json
import math
import queue
import random
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone

try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext
except ImportError as exc:
    raise SystemExit("缺少 Tkinter。请安装 tk 支持后重试（Python 通常自带）。") from exc

VERSION = "1.0.0"

# 与固件默认保持一致（见 main/coaster_main.c）
FW_DEFAULT_SCALE = 384.7
FW_DEFAULT_REMINDER_MIN = 45

MAX_EVENTS = 500
MAX_CMDS = 50

# 深色配色
C_BG = "#0e1116"
C_PANEL = "#161b22"
C_PANEL2 = "#1c232c"
C_LINE = "#2a323d"
C_TXT = "#e6edf3"
C_MUT = "#8b97a7"
C_OK = "#56d364"
C_WARN = "#e3b341"
C_BAD = "#f85149"
C_CUP = "#79c0ff"
C_BOT = "#3fb6c4"


# --------------------------------------------------------------------------- #
# 状态模型
# --------------------------------------------------------------------------- #

class State:
    """线程安全：串口线程只写，UI 线程读/刷新。"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.connected = False
        self.mode = "boot"
        self.mode_detail = ""
        self.port = ""
        self.baud = 115200
        self.last_line = ""
        self.last_json = None
        self.last_ts = 0.0
        self.serial_errors = 0
        self.weight_g = None
        self.state_name = "no_cup"
        self.session_ml = 0.0
        self.since_drink_min = 0
        self.last_status_ts = 0.0
        self.config = {
            "scale": FW_DEFAULT_SCALE,
            "reminder_min": FW_DEFAULT_REMINDER_MIN,
            "estimate_on_refill": True,
            "baseline_raw": None,
            "min_cup_g": None,
            "configured": False,
        }
        self.events: "deque[dict]" = deque(maxlen=MAX_EVENTS)
        self.commands: "deque[dict]" = deque(maxlen=MAX_CMDS)

    def add_event(self, ev: dict) -> None:
        with self.lock:
            ev = dict(ev)
            ev["ts"] = time.time()
            ev["t"] = datetime.fromtimestamp(ev["ts"], tz=timezone.utc).astimezone().isoformat()
            self.events.appendleft(ev)

    def snapshot(self) -> dict:
        with self.lock:
            cfg = dict(self.config)
            return {
                "mode": self.mode,
                "mode_detail": self.mode_detail,
                "port": self.port,
                "connected": self.connected,
                "last_ts": self.last_ts,
                "weight_g": self.weight_g,
                "state": self.state_name,
                "session_ml": self.session_ml,
                "since_drink_min": self.since_drink_min,
                "reminder_min": cfg.get("reminder_min"),
                "config": cfg,
                "events": list(self.events),
                "commands": list(self.commands),
                "serial_errors": self.serial_errors,
            }


# --------------------------------------------------------------------------- #
# 设备（串口 / 模拟器）
# --------------------------------------------------------------------------- #

class SerialDevice:
    """基于 pyserial 的真机串口读写。"""

    def __init__(self, port: str, baud: int, on_line, on_error) -> None:
        self.port = port
        self.baud = baud
        self._ser = None
        self._buf = b""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.on_line = on_line
        self.on_error = on_error

    def start(self) -> None:
        import serial  # 延迟导入

        self._ser = serial.Serial(self.port, self.baud, timeout=0.2)
        self._stop.clear()
        self._thread = threading.Thread(target=self._read_loop,
                                        name="coaster-serial", daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        import serial as _s

        while not self._stop.is_set():
            try:
                data = self._ser.read(512)
            except _s.SerialException as exc:
                if self.on_error:
                    self.on_error(f"{self.port}: {exc}")
                return
            if not data:
                continue
            self._buf += data
            while b"\n" in self._buf:
                raw, self._buf = self._buf.split(b"\n", 1)
                line = raw.decode("utf-8", errors="replace").strip()
                if line and self.on_line:
                    try:
                        self.on_line(line)
                    except Exception as exc:
                        if self.on_error:
                            self.on_error(f"handle: {exc}")

    def write(self, line: str) -> bool:
        if not self._ser:
            return False
        try:
            self._ser.write(line.encode("utf-8"))
            return True
        except Exception as exc:
            if self.on_error:
                self.on_error(f"{self.port}: write failed ({exc})")
            return False

    def close(self) -> None:
        self._stop.set()
        try:
            if self._ser:
                self._ser.close()
        except Exception:
            pass


class SimDevice:
    """模拟器：生成与固件字段一致的 JSON Lines，用于无板演示。

    状态机刻意接近固件：NO_CUP / SETTLING / STABLE，
    放杯 → 稳定并报 cup_placed → 在位喝水 → 加水 → 拿起报 cup_removed。
    """

    def __init__(self, on_line, on_error=None) -> None:
        self.on_line = on_line
        self.on_error = on_error
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.clock = 0
        self.state_name = "no_cup"
        self.config = {
            "scale": FW_DEFAULT_SCALE,
            "reminder_min": FW_DEFAULT_REMINDER_MIN,
            "estimate_on_refill": 1,
            "baseline_raw": 0,
            "min_cup_g": 0.0,
        }

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="coaster-sim", daemon=True)
        self._thread.start()

    def write(self, line: str) -> bool:
        obj = parse_line(line)
        if obj is None:
            return False
        cmd = obj.get("cmd")
        if cmd == "get_config":
            self._emit({"config": dict(self.config)})
            return True
        ok = False
        if cmd == "set_reminder" and type(obj.get("minutes")) is int:
            minutes = obj["minutes"]
            if 0 <= minutes <= 0xFFFFFFFF:
                self.config["reminder_min"] = minutes
                ok = True
        elif cmd == "set_scale" and type(obj.get("value")) in (int, float):
            value = obj["value"]
            if math.isfinite(value) and 0 < value <= 1000000:
                self.config["scale"] = value
                ok = True
        elif cmd == "estimate_on_refill" and type(obj.get("value")) is bool:
            self.config["estimate_on_refill"] = int(obj["value"])
            ok = True
        elif cmd == "calibrate_empty" and self.state_name == "no_cup":
            ok = True
        self._emit({"ack": cmd, "ok": int(ok)})
        return True

    def close(self) -> None:
        self._stop.set()

    def _emit(self, obj: dict) -> None:
        try:
            self.on_line(json.dumps(obj, separators=(",", ":")) + "\n")
        except Exception:
            pass

    def _status(self, weight: float, state: str, session: float) -> None:
        self.state_name = state
        self._emit({
            "status": {
                "weight_g": weight,
                "state": state,
                "session_ml": session,
                "since_drink_min": self.clock,
            }
        })

    def _run(self) -> None:
        rnd = random.Random(20261107)
        phase = "drift"
        timer = 0
        session = 0.0
        target = 330.0
        empty = 0.5

        while not self._stop.is_set():
            self._stop.wait(1.0)
            timer += 1
            self.clock += 1

            if phase == "drift":
                w = rnd.uniform(0.2, 1.5)
                self._status(w, "no_cup", session)
                if timer > 3:
                    phase, timer = "place", 0
                    target = rnd.uniform(260.0, 430.0)
            elif phase == "place":
                w = empty + (target - empty) * min(timer / 3.0, 1.0)
                st_name = "settling" if timer < 3 else "stable"
                if timer == 3:
                    self._emit({"event": "cup_placed", "weight_g": round(target, 1)})
                elif timer > 8:
                    phase, timer = "drink", 0
                self._status(w, st_name, session)
            elif phase == "drink":
                if timer == 1:
                    take = rnd.uniform(40.0, 180.0)
                    self._emit({"event": "drink", "ml": round(take, 1),
                                "estimated": 0, "weight_g": round(target - take, 1)})
                    session += take
                    target -= take
                    self.clock = 0
                elif timer == 4 and rnd.random() < 0.7:
                    add = rnd.uniform(30.0, 120.0)
                    self._emit({"event": "refill", "ml": round(add, 1),
                                "weight_g": round(target + add, 1)})
                    target += add
                if timer > 8:
                    phase, timer = "remove", 0
                self._status(target, "stable", session)
            elif phase == "remove":
                self._emit({"event": "cup_removed", "weight_g": round(target, 1)})
                empty = 0.5
                self._status(empty, "no_cup", session)
                phase, timer = "drift", 0

            if self.clock >= 45 and timer == 1:
                self._emit({"event": "remind", "since_drink_min": self.clock})
                self.clock = 0


# --------------------------------------------------------------------------- #
# 协议解析（与固件 JSON Lines 对齐）
# --------------------------------------------------------------------------- #

def parse_line(line: str):
    line = line.strip()
    if not line or line[0] != "{":
        return None                      # ESP_LOG 等非 JSON 行忽略
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def apply_frame(st: State, obj: dict) -> None:
    with st.lock:
        st.last_line = json.dumps(obj, separators=(",", ":"))
        st.last_ts = time.time()
        st.last_json = obj
        st.connected = True

    if "status" in obj:
        s = obj["status"]
        with st.lock:
            st.weight_g = s.get("weight_g")
            st.state_name = s.get("state", "unknown")
            st.session_ml = s.get("session_ml", 0.0)
            st.since_drink_min = s.get("since_drink_min", 0)
            st.last_status_ts = time.time()

    elif "config" in obj:
        cfg = obj["config"]
        with st.lock:
            for k in ("scale", "reminder_min", "estimate_on_refill",
                      "baseline_raw", "min_cup_g"):
                if k in cfg:
                    st.config[k] = cfg[k]
            st.config["configured"] = True

    elif "ack" in obj:
        with st.lock:
            st.commands.appendleft({
                "t": datetime.now().strftime("%H:%M:%S"),
                "cmd": obj.get("ack"),
                "ok": bool(obj.get("ok")),
            })
        return

    elif obj.get("event"):
        ev_type = obj.get("event")
        if ev_type == "remind":
            ev = {"kind": ev_type, "since_drink_min": obj.get("since_drink_min")}
        else:
            ev = {
                "kind": ev_type,
                "weight_g": obj.get("weight_g"),
                "ml": obj.get("ml", obj.get("drink_ml", obj.get("refill_ml"))),
                "estimated": obj.get("estimated", False),
            }
        st.add_event(ev)


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #

class CommandManager:
    """把 UI 命令翻译为串口命令。"""

    def __init__(self, device) -> None:
        self.device = device
        self.device_ready = device is not None

    def _send(self, payload: dict) -> dict:
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        if not self.device.write(line):
            return {"ok": False, "error": "串口写入失败"}
        return {"ok": True, "note": "等待设备回复"}

    def dispatch(self, cmd, params: dict) -> dict:
        if not cmd:
            return {"ok": False, "error": "缺少 cmd"}
        if not self.device_ready or self.device is None:
            return {"ok": False, "error": "设备未就绪"}

        if cmd == "set_reminder":
            minutes = params.get("minutes")
            if type(minutes) is not int or minutes < 0 or minutes > 0xFFFFFFFF:
                return {"ok": False, "error": "minutes 须为整数且 >= 0"}
            return self._send({"cmd": "set_reminder", "minutes": minutes})

        if cmd == "set_scale":
            value = params.get("value")
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or value <= 0 or value > 1000000):
                return {"ok": False, "error": "value 须 > 0"}
            return self._send({"cmd": "set_scale", "value": float(value)})

        if cmd == "estimate_on_refill":
            value = params.get("value")
            if not isinstance(value, bool):
                return {"ok": False, "error": "value 须为布尔值"}
            return self._send({"cmd": "estimate_on_refill", "value": value})

        if cmd == "calibrate_empty":
            return self._send({"cmd": "calibrate_empty"})

        if cmd == "get_config":
            return self._send({"cmd": "get_config"})

        if cmd == "reset_session":
            return {"ok": False, "error": "不支持：会话累计在设备侧，请重启设备"}

        return {"ok": False, "error": f"未知命令 {cmd!r}"}


class CoasterApp(tk.Tk):
    def __init__(self, device, st: State, msgq: "queue.Queue") -> None:
        super().__init__()
        self.device = device
        self.st = st
        self.msgq = msgq
        self.cmd = CommandManager(device)

        self.title(f"智能杯垫上位机 v{VERSION}")
        self.minsize(940, 660)
        self.configure(bg=C_BG)

        try:
            self.style = ttk.Style(self)
            self.style.theme_use("clam")
        except tk.TclError:
            self.style = ttk.Style()

        # 进度条两种配色：正常(蓝) / 已超阈值(红)
        self.style.configure("coast.meter.Horizontal.TProgressbar",
                             troughcolor=C_BOT, background=C_BOT,
                             bordercolor=C_BOT, lightcolor=C_BOT, darkcolor=C_BOT)
        self.style.configure("coast.alert.Horizontal.TProgressbar",
                             troughcolor=C_BAD, background=C_BAD,
                             bordercolor=C_BAD, lightcolor=C_BAD, darkcolor=C_BAD)
        self.meter_style_normal = "coast.meter.Horizontal.TProgressbar"
        self.meter_style_alert = "coast.alert.Horizontal.TProgressbar"

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(300, self._drain)

    # ---- 控件构建 ----
    def _build_ui(self) -> None:
        # 顶部
        top = tk.Frame(self, bg=C_BG)
        top.pack(fill="x", padx=14, pady=(12, 6))
        self.var_title = tk.StringVar(value="智能杯垫 · USB 串口实时面板")
        tk.Label(top, textvariable=self.var_title, bg=C_BG, fg=C_TXT,
                 font=("Microsoft YaHei", 13, "bold")).pack(side="left")
        self.var_mode = tk.StringVar(value="模式 -")
        self.var_conn = tk.StringVar(value="● 未连接")
        self.badge_mode = tk.Label(top, textvariable=self.var_mode, bg=C_PANEL2,
                                   fg=C_MUT, bd=1, relief="solid", padx=10, pady=4)
        self.badge_mode.pack(side="right", padx=6)
        self.badge_conn = tk.Label(top, textvariable=self.var_conn, bg=C_PANEL2,
                                   fg=C_MUT, bd=1, relief="solid", padx=10, pady=4)
        self.badge_conn.pack(side="right")

        body = tk.Frame(self, bg=C_BG)
        body.pack(fill="both", expand=True)

        # 左：称重卡片
        left = tk.Frame(body, bg=C_BG)
        left.pack(side="left", fill="both", expand=True, padx=(14, 6), pady=6)

        card_w = self._card(left, "实时称重")
        inner = tk.Frame(card_w, bg=C_PANEL)
        inner.pack(fill="both", expand=True, padx=12, pady=6)

        gauge = tk.Frame(inner, bg=C_PANEL)
        gauge.pack(side="left", fill="y")
        self.canvas = tk.Canvas(gauge, width=150, height=130, bg=C_PANEL,
                                highlightthickness=0)
        self.canvas.pack(side="top")
        self.var_weight = tk.StringVar(value="--")
        tk.Label(gauge, textvariable=self.var_weight, bg=C_PANEL, fg=C_TXT,
                 font=("Consolas", 32, "bold")).pack(side="top")
        self.var_state = tk.StringVar(value="no_cup")
        self.state_chip = tk.Label(gauge, textvariable=self.var_state, bg=C_PANEL2,
                                   fg=C_MUT, bd=1, relief="solid", padx=8, pady=3)
        self.state_chip.pack(side="top", pady=(4, 0))

        meter = tk.Frame(inner, bg=C_PANEL)
        meter.pack(side="left", fill="x", expand=True, padx=(16, 0))
        self.var_remleft = tk.StringVar(value="--")
        tk.Label(meter, textvariable=self.var_remleft, bg=C_PANEL, fg=C_TXT,
                 font=("Microsoft YaHei", 11)).pack(anchor="w")
        self.meter = ttk.Progressbar(meter, mode="determinate", maximum=100)
        self.meter.pack(fill="x", pady=4)
        self.var_hint = tk.StringVar(value="等待设备上报 …")
        tk.Label(meter, textvariable=self.var_hint, bg=C_PANEL, fg=C_MUT,
                 font=("Microsoft YaHei", 9), wraplength=250, justify="left").pack(anchor="w")

        stats = tk.Frame(inner, bg=C_PANEL)
        stats.pack(fill="x", pady=(10, 0))

        def stat_block(col: int, title: str, var: tk.StringVar, fg: str) -> None:
            tk.Label(stats, text=title, bg=C_PANEL2, fg=C_MUT, bd=1, relief="solid",
                     padx=12, pady=5, font=("Microsoft YaHei", 9)).grid(row=1, column=col, padx=6, ipady=2)
            tk.Label(stats, textvariable=var, bg=C_PANEL2, fg=fg, bd=1, relief="solid",
                     padx=12, pady=5, font=("Consolas", 16, "bold")).grid(row=0, column=col, padx=6)

        self.var_session = tk.StringVar(value="0")
        stat_block(0, "本次饮水 (ml)", self.var_session, C_CUP)
        self.var_since = tk.StringVar(value="--")
        stat_block(1, "距上次喝水", self.var_since, C_WARN)
        self.var_remindermin = tk.StringVar(value="--")
        stat_block(2, "提醒阈值", self.var_remindermin, C_OK)

        self.var_session.set("0")

        # 右：配置 + 命令
        right = tk.Frame(body, bg=C_BG)
        right.pack(side="left", fill="y", padx=(6, 14), pady=6)

        cfg_card = self._card(right, "配置下发")
        c = tk.Frame(cfg_card, bg=C_PANEL)
        c.pack(fill="x", padx=12, pady=8)

        tk.Label(c, text="喝水提醒间隔(min, 0=关)", bg=C_PANEL, fg=C_MUT,
                 font=("Microsoft YaHei", 9)).pack(anchor="w")
        self.in_minutes = tk.Entry(c, width=8, bg=C_PANEL2, fg=C_TXT, insertbackground=C_TXT)
        self.in_minutes.insert(0, "45")
        self.in_minutes.pack(anchor="w")
        self.btn_rem = tk.Button(c, text="保存提醒", command=self._on_reminder)
        self.btn_rem.pack(fill="x")

        tk.Label(c, text="空杯/校准系数 scale", bg=C_PANEL, fg=C_MUT,
                 font=("Microsoft YaHei", 9)).pack(anchor="w", pady=(8, 0))
        self.in_scale = tk.Entry(c, width=8, bg=C_PANEL2, fg=C_TXT, insertbackground=C_TXT)
        self.in_scale.insert(0, f"{FW_DEFAULT_SCALE}")
        self.in_scale.pack(anchor="w")
        tk.Button(c, text="设置系数", command=self._on_scale).pack(fill="x")

        self.var_est = tk.BooleanVar(value=True)
        self.cb_est = tk.Checkbutton(c, text="续杯时按已喝光估算喝水量", bg=C_PANEL,
                                     fg=C_TXT, variable=self.var_est,
                                     activebackground=C_PANEL, selectcolor=C_PANEL2)
        self.cb_est.pack(anchor="w", pady=(8, 0))
        btns = tk.Frame(c, bg=C_PANEL)
        btns.pack(fill="x", pady=(4, 0))
        tk.Button(btns, text="应用估算开关", command=self._on_estimate).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="读取配置", command=self._on_getconfig).pack(side="left", padx=6)
        tk.Button(btns, text="空载校准", command=self._on_calibrate).pack(side="left")
        self.var_hintcfg = tk.StringVar(value="")
        tk.Label(c, textvariable=self.var_hintcfg, bg=C_PANEL, fg=C_MUT,
                 font=("Microsoft YaHei", 9), wraplength=230, justify="left").pack(anchor="w", pady=(6, 0))

        cmd_card = self._card(right, "命令结果")
        cc = tk.Frame(cmd_card, bg=C_PANEL)
        cc.pack(fill="both", expand=True, padx=12, pady=8)
        self.cmd_log = scrolledtext.ScrolledText(cc, height=5, bg=C_BG, fg=C_MUT,
                                                font=("Consolas", 9), wrap="word", relief="solid")
        self.cmd_log.pack(fill="both", expand=True)

        # 底部：事件流
        ev = self._card(self, "事件流（喝水 / 加水 / 提醒 / 放杯）")
        ec = tk.Frame(ev, bg=C_PANEL)
        ec.pack(fill="both", expand=True, padx=12, pady=8)
        self.ev_log = scrolledtext.ScrolledText(ec, height=8, bg=C_BG, fg=C_TXT,
                                               font=("Consolas", 10), wrap="word", relief="solid")
        self.ev_log.pack(fill="both", expand=True)

        self._last_ev = None
        self._last_cmd = None
        self._last_config = None

    def _card(self, parent, title: str) -> tk.Frame:
        card = tk.Frame(parent, bg=C_PANEL, bd=1, relief="solid",
                        borderwidth=1, highlightbackground=C_LINE, highlightthickness=1)
        tk.Label(card, text=title, bg=C_PANEL, fg=C_MUT,
                 font=("Microsoft YaHei", 9, "bold")).pack(anchor="w", padx=12, pady=(8, 0))
        card.pack(fill="both", expand=True, pady=6)
        return card

    # ---- 业务动作 ----
    def _on_reminder(self) -> None:
        try:
            minutes = int(self.in_minutes.get().strip())
        except ValueError:
            self._toast_err("minutes 输入非法")
            return
        self.send_command("set_reminder", minutes=minutes)

    def _on_scale(self) -> None:
        try:
            value = float(self.in_scale.get().strip())
        except ValueError:
            self._toast_err("scale 输入非法")
            return
        self.send_command("set_scale", value=value)

    def _on_estimate(self) -> None:
        self.send_command("estimate_on_refill", value=bool(self.var_est.get()))

    def _on_getconfig(self) -> None:
        self.send_command("get_config")

    def _on_calibrate(self) -> None:
        self.send_command("calibrate_empty")

    def send_command(self, name: str, **params) -> None:
        try:
            result = self.cmd.dispatch(name, params)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        rec = {
            "t": datetime.now().strftime("%H:%M:%S"),
            "cmd": name,
            "ok": bool(result.get("ok")),
            "note": result.get("note", ""),
            "error": result.get("error", ""),
        }
        with self.st.lock:
            self.st.commands.appendleft(rec)
        self._append_cmd_log(rec)
        self._toast(result.get("note", ""), not result.get("ok"))
        self._refresh_cmd_from_state()

    # ---- 后台消息队列 ----
    def _drain(self) -> None:
        # 无论消费或刷新是否出错，都必须续排，否则界面数据会停更
        try:
            while True:
                kind, payload = self.msgq.get_nowait()
                if kind == "line":
                    apply_frame(self.st, payload)
                    if (payload.get("ack") in {"set_reminder", "set_scale",
                                              "estimate_on_refill", "calibrate_empty"}
                            and payload.get("ok")):
                        self.cmd.dispatch("get_config", {})
                elif kind == "error":
                    with self.st.lock:
                        if self.st.mode != "error":
                            self.st.mode = "error"
                            self.st.mode_detail = str(payload)
        except queue.Empty:
            pass
        finally:
            self.after(300, self._drain)
        try:
            self._refresh()
        except Exception as exc:  # 绘图异常不得影响数据流
            self.var_hint.set(f"[渲染异常] {exc}")

    # ---- 刷新 ----
    def _refresh(self) -> None:
        s = self.st.snapshot()
        mode = s.get("mode") or "--"
        detail = s.get("mode_detail") or ""
        self.var_mode.set(f"模式 {mode}" + (f" · {detail}" if detail else ""))
        if mode == "error":
            self.badge_mode.configure(fg=C_BAD)
        else:
            self.badge_mode.configure(fg=C_MUT)
        self.var_conn.set("● 已连接" if s.get("connected") else "● 未连接")
        self.badge_conn.configure(fg=C_OK if s.get("connected") else C_BAD)

        w = s.get("weight_g")
        self.var_weight.set(f"{w:.1f}".rstrip("0").rstrip(".") if w is not None else "--")
        self.var_state.set(s.get("state", "no_cup"))
        st_name = s.get("state", "no_cup")
        if st_name == "stable":
            self.state_chip.configure(fg=C_OK)
        elif st_name == "settling":
            self.state_chip.configure(fg=C_WARN)
        else:
            self.state_chip.configure(fg=C_MUT)

        self.var_session.set(str(int(round(s.get("session_ml", 0.0)))))
        self.var_since.set(str(s.get("since_drink_min", 0)))
        rm = s.get("reminder_min")
        self.var_remindermin.set(str(rm) if rm is not None else "--")

        since = s.get("since_drink_min", 0)
        if rm and rm > 0:
            left = max(0, rm - since)
            self.var_remleft.set(f"距提醒还有 {left} min")
            ratio = min(1.0, since / rm)
        else:
            self.var_remleft.set("提醒已关闭")
            ratio = min(1.0, since / 45.0)
        self.meter.configure(value=round(ratio * 100))
        if rm and rm > 0 and since >= rm:
            self.meter.configure(style=self.meter_style_alert)
        else:
            self.meter.configure(style=self.meter_style_normal)

        cfg = s.get("config") or {}
        if cfg.get("configured") and cfg != self._last_config:
            self._last_config = dict(cfg)
            self.in_minutes.delete(0, "end")
            self.in_minutes.insert(0, str(cfg.get("reminder_min", "")))
            self.in_scale.delete(0, "end")
            self.in_scale.insert(0, str(cfg.get("scale", "")))
            if cfg.get("estimate_on_refill") is not None:
                self.var_est.set(bool(cfg.get("estimate_on_refill")))
            base = cfg.get("baseline_raw")
            mincup = cfg.get("min_cup_g")
            self.var_hintcfg.set(
                f"scale={cfg.get('scale')} · baseline={base} · min_cup={mincup}g"
            )

        self._refresh_events(s.get("events") or [])
        self._refresh_cmd_from_state()
        self._draw_cup(s.get("weight_g"))

    # ---- 绘图 ----
    def _draw_cup(self, weight_g) -> None:
        c = self.canvas
        c.delete("all")
        if weight_g is None:
            weight_g = 0.0
        # 杯身
        c.create_rectangle(60, 26, 150, 104, outline=C_CUP, width=3)
        # 把手
        c.create_arc(146, 36, 200, 96, start=270, extent=180, style="arc",
                     outline=C_CUP, width=3)
        # 液面
        ratio = max(0.0, min(1.0, weight_g / 500.0))
        if ratio > 0.01:
            liq_top = 100 - (100 - 30) * ratio
            c.create_rectangle(63, liq_top, 147, 97, fill=C_BOT, outline="")
        # 杯口
        c.create_line(58, 24, 152, 24, fill=C_CUP, width=4)
        # 空载提示
        if weight_g < 25:
            c.create_text(105, 122, text="杯垫空载", fill=C_MUT, font=("Microsoft YaHei", 8))

    # ---- 日志 ----
    def _refresh_events(self, events: list) -> None:
        if events == self._last_ev:
            return
        self._last_ev = events
        self._render_events(events[:60])

    def _render_events(self, events: list) -> None:
        self.ev_log.delete("1.0", "end")
        for ev in reversed(events):  # 最新在前
            kind = ev.get("kind", "?")
            if kind == "drink":
                detail = f'+{_fmt(ev.get("ml"), 0)} ml'
            elif kind == "refill":
                detail = f'+{_fmt(ev.get("ml"), 0)} ml 水'
            elif kind == "remind":
                detail = f'无饮水 {ev.get("since_drink_min")} min'
            elif kind in ("cup_placed", "cup_removed"):
                detail = f'{_fmt(ev.get("weight_g"), 0)} g'
            else:
                detail = ""
            when = (ev.get("t") or "")[11:16]
            self.ev_log.insert("end", f"{when}  {kind:<12} {detail}\n")
        self.ev_log.see("end")

    def _refresh_cmd_from_state(self) -> None:
        s = self.st.snapshot()
        cmds = s.get("commands") or []
        if hasattr(self, "_last_cmd") and cmds == self._last_cmd:
            return
        self._last_cmd = cmds
        self._render_cmds(cmds[:12])

    def _render_cmds(self, cmds: list) -> None:
        self.cmd_log.delete("1.0", "end")
        for c in cmds:
            mark = "OK" if c.get("ok") else "XX"
            note = c.get("note") or c.get("error") or ""
            self.cmd_log.insert("end", f"{c.get('t', '')}  [{mark}] {c.get('cmd')}  {note}\n")

    def _append_cmd_log(self, rec: dict) -> None:
        mark = "OK" if rec.get("ok") else "XX"
        note = rec.get("note") or rec.get("error") or ""
        self.cmd_log.insert("end", f"{rec.get('t', '')}  [{mark}] {rec.get('cmd')}  {note}\n")
        self.cmd_log.see("end")

    # ---- 提示 ----
    def _toast(self, msg: str, err: bool = False) -> None:
        # Tkinter 无内置 toast；直接写入左栏状态条
        self.var_hint.set(("[错误] " if err else "") + msg)

    def _toast_err(self, msg: str) -> None:
        self.var_hint.set("[错误] " + msg)

    # ---- 关闭 ----
    def _on_close(self) -> None:
        try:
            if self.device:
                self.device.close()
        except Exception:
            pass
        self.destroy()

    # ---- 无界面自检 ----
    def run_selftest(self, seconds: int) -> int:
        with self.st.lock:
            self.st.mode = "sim" if isinstance(self.device, SimDevice) else "serial"
            self.st.mode_detail = getattr(self.device, "port", "sim")
            self.st.port = getattr(self.device, "port", "")
        self.withdraw()
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                self.update()
            except tk.TclError:
                break
        s = self.st.snapshot()
        # 模拟器需产出至少一个事件；真机只要求连上且收到重量（静置时可能只发 status）
        ok = (s.get("weight_g") is not None) and s.get("connected")
        if isinstance(self.device, SimDevice):
            ok = ok and bool(s.get("events"))
        print(f"[selftest] lines_weight={s.get('weight_g') is not None} "
              f"events={len(s.get('events') or [])} connected={s.get('connected')} "
              f"=> {'PASS' if ok else 'FAIL'}")
        print("[selftest-logic]")
        ok = logic_selftest() and ok
        try:
            self.device.close()
        except Exception:
            pass
        return 0 if ok else 1


def _fmt(v, digits=1):
    if v is None:
        return "--"
    return f"{float(v):.{digits}f}".rstrip("0").rstrip(".")


class _FakeDev:
    """记录 write 调用的假设备，用于离线测试 CommandManager。"""

    def __init__(self) -> None:
        self.sent = []
        self.writable = True

    def write(self, line: str) -> bool:
        self.sent.append(line)
        return self.writable

    def close(self) -> None:
        pass


def logic_selftest() -> bool:
    """脱离窗口验证：协议解析、状态落库、命令合法性。"""
    ok = True

    def check(name, cond):
        nonlocal ok
        if cond:
            print(f"  [ok] {name}")
        else:
            print(f"  [fail] {name}")
            ok = False

    # 1) 行解析
    check("忽略非 JSON 行(ESP_LOG)", parse_line("I (3) app: hello") is None)
    check("忽略空行", parse_line("") is None)
    check("忽略非法 JSON", parse_line("not json") is None)
    obj = parse_line('{"event":"drink","ml":150.0,"estimated":0}')
    check("解析合法 JSON", isinstance(obj, dict) and obj.get("ml") == 150.0)

    # 2) 状态落库
    st = State()
    apply_frame(st, {"status": {"weight_g": 250.5, "state": "stable",
                              "session_ml": 300.0, "since_drink_min": 12}})
    check("status -> weight_g", st.weight_g == 250.5)
    check("status -> state_name", st.state_name == "stable")
    check("status -> connected", st.connected is True)

    apply_frame(st, {"event": "drink", "ml": 40.0, "estimated": 0, "weight_g": 210.5})
    check("event -> 记入 events", len(st.events) == 1 and st.events[0]["kind"] == "drink")

    apply_frame(st, {"ack": "set_reminder", "ok": 1})
    check("ack -> 记入 commands", len(st.commands) == 1 and st.commands[0]["cmd"] == "set_reminder")

    apply_frame(st, {"config": {"scale": 384.7, "reminder_min": 30,
                              "estimate_on_refill": False}})
    check("config -> 落库", st.config["reminder_min"] == 30 and st.config["configured"])

    # 3) 命令合法性
    dev = _FakeDev()
    cm = CommandManager(dev)
    check("set_reminder 合法", cm.dispatch("set_reminder", {"minutes": 30})["ok"])
    check("set_reminder 负数拒绝", cm.dispatch("set_reminder", {"minutes": -1})["ok"] is False)
    check("set_reminder 非整拒绝", cm.dispatch("set_reminder", {"minutes": 1.5})["ok"] is False)
    check("set_scale 合法", cm.dispatch("set_scale", {"value": 385.0})["ok"])
    check("set_scale 非正数拒绝", cm.dispatch("set_scale", {"value": 0})["ok"] is False)
    check("estimate 布尔合法", cm.dispatch("estimate_on_refill", {"value": True})["ok"])
    check("estimate 非布尔拒绝", cm.dispatch("estimate_on_refill", {"value": "yes"})["ok"] is False)
    check("未知命令拒绝", cm.dispatch("nope", {})["ok"] is False)
    check("空命令拒绝", cm.dispatch(None, {})["ok"] is False)
    check("set_reminder 写串口", any("set_reminder" in x for x in dev.sent))
    check("命令以换行结尾", all(x.endswith("\n") for x in dev.sent))
    check("set_reminder 拒绝布尔值", cm.dispatch("set_reminder", {"minutes": True})["ok"] is False)
    check("set_scale 拒绝非有限值", cm.dispatch("set_scale", {"value": float("nan")})["ok"] is False)
    dev.writable = False
    check("串口写失败如实报告", cm.dispatch("get_config", {})["ok"] is False)

    frames = []
    sim = SimDevice(frames.append)
    check("模拟器接受提醒配置", sim.write('{"cmd":"set_reminder","minutes":0}\n'))
    check("模拟器返回成功回包", parse_line(frames[-1])["ok"] == 1)
    sim.write('{"cmd":"get_config"}\n')
    check("模拟器回读配置", parse_line(frames[-1])["config"]["reminder_min"] == 0)
    return ok


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #

def list_ports() -> None:
    try:
        from serial.tools import list_ports
        ports = [p.device for p in list_ports.comports()]
    except Exception as exc:
        print("无法列举串口（未安装 pyserial？）：", exc)
        return
    print("可用串口：" + ", ".join(ports) if ports else "未发现串口")


def build_device(args, msgq: "queue.Queue", st: State):
    def on_error(msg: str) -> None:
        print(f"[err] {msg}", flush=True)
        with st.lock:
            st.serial_errors += 1
            st.connected = False
            st.mode = "error"
            st.mode_detail = msg
        msgq.put(("error", msg))

    def on_line(line: str) -> None:
        obj = parse_line(line)
        if obj is not None:
            msgq.put(("line", obj))

    if args.simulate or (args.port and args.port.lower() == "sim"):
        print("模式：模拟器（未连接真机）", flush=True)
        dev = SimDevice(on_line, on_error)
        dev.start()
        return dev

    if not args.port:
        raise SystemExit("请用 --port 指定串口，或 --list 查看，或 --simulate 演示")

    print(f"模式：真机串口 {args.port} @ {args.baud}", flush=True)
    dev = SerialDevice(args.port, args.baud, on_line, on_error)
    dev.start()
    return dev


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="智能杯垫上位机（USB 串口 JSON Lines → 桌面面板）")
    ap.add_argument("--port", "-p", default="sim",
                    help='串口名，如 COM18；或 "sim" 进入模拟器（默认）')
    ap.add_argument("--baud", "-b", type=int, default=115200,
                    help="串口波特率（USB CDC 实际忽略，默认 115200）")
    ap.add_argument("--simulate", action="store_true",
                    help="强制使用模拟器")
    ap.add_argument("--list", action="store_true", help="仅列举可用串口后退出")
    ap.add_argument("--selftest", type=int, metavar="SECONDS", default=0,
                    help="无界面自检：以模拟器运行 N 秒，再跑逻辑自检")
    ap.add_argument("--logic-test", action="store_true",
                    help="只跑协议/命令逻辑自检（不启动窗口、不需要串口）")
    args = ap.parse_args(argv)

    if args.list:
        list_ports()
        return 0

    if args.logic_test:
        return 0 if logic_selftest() else 1

    st = State()
    msgq: "queue.Queue" = queue.Queue()

    try:
        device = build_device(args, msgq, st)
    except SystemExit as exc:
        print(exc, flush=True)
        return 1
    except ImportError:
        print("缺少 pyserial。请执行：pip install pyserial", flush=True)
        return 1

    with st.lock:
        st.mode = "sim" if isinstance(device, SimDevice) else "serial"
        st.mode_detail = getattr(device, "port", "sim")
        st.port = getattr(device, "port", "")

    app = CoasterApp(device, st, msgq)

    if args.selftest > 0:
        return app.run_selftest(args.selftest)

    app.mainloop()
    try:
        device.close()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
