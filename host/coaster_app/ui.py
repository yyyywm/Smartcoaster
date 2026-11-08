"""Tkinter dashboard and fullscreen drinking reminder."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import math
import queue
import time

from .dpi import enable_native_dpi

enable_native_dpi()

import tkinter as tk
from tkinter import filedialog, ttk

from .model import HydrationCore, Settings
from .storage import Store
from .transport import DemoFeed, SerialFeed, available_ports


BG = "#101820"
PANEL = "#1A2630"
PANEL_ALT = "#22333D"
TEXT = "#F4F2EA"
MUTED = "#A9B7BB"
ACCENT = "#65D6A6"
WATER = "#5FB9DC"
ALERT = "#FFB86B"
RECORDS_PAGE_SIZE = 10


class App(tk.Tk):
    def __init__(self, store: Store, feed, messages: queue.Queue):
        super().__init__()
        self.store = store
        self.feed = feed
        self.demo_mode = isinstance(feed, DemoFeed)
        self.messages = messages
        settings = store.load_settings()
        last, alert, progress = store.load_runtime()
        self.core = HydrationCore(settings, last, alert, progress)
        self._restored_alert_started = alert
        self.weight_g: float | None = None
        self.device_state = "unknown"
        self.connection = False
        self.connection_detail = "连接中"
        self.calibration_sync_error = False
        self.last_frame_at: datetime | None = None
        self.alert_window: tk.Toplevel | None = None
        self._closing = False
        self._tick_jobs: list[str] = []
        self.tare_pending: tuple[float, float] | None = None
        self.full_pending: tuple[float, float] | None = None
        self.records_page = 0
        self.records_dirty = True
        self.delete_pending: tuple[str, float, tuple[int, ...]] | None = None

        self.title("智能杯垫 · 饮水提醒")
        self.configure(bg=BG)
        width = min(1100, self.winfo_screenwidth() - 80)
        height = min(600, self.winfo_screenheight() - 120)
        left = max(0, (self.winfo_screenwidth() - width) // 2)
        top = max(0, (self.winfo_screenheight() - height - 60) // 2)
        self.geometry(f"{width}x{height}+{left}+{top}")
        self.minsize(1100, 600)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind_all("<Control-Shift-Q>", self._emergency_exit)
        self._build()
        self.feed.start()
        self._schedule_tick(250)

    def _schedule_tick(self, delay_ms: int) -> None:
        self._tick_jobs.append(self.after(delay_ms, self._tick))

    def _label(self, parent, text: str, size: int = 11, color: str = TEXT,
               bold: bool = False, **kwargs) -> tk.Label:
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=("Microsoft YaHei UI", size, "bold" if bold else "normal"),
                        **kwargs)

    def _panel(self, parent, title: str) -> tk.Frame:
        panel = tk.Frame(parent, bg=PANEL, padx=14, pady=10,
                         highlightthickness=1, highlightbackground="#31424A")
        self._label(panel, title, 10, MUTED, True).pack(anchor="w", pady=(0, 7))
        return panel

    def _build(self) -> None:
        settings = self.core.settings
        page = tk.Frame(self, bg=BG)
        page.pack(fill="both", expand=True)

        top = tk.Frame(page, bg=BG)
        top.pack(fill="x", padx=18, pady=(10, 6))
        self._label(top, "智能杯垫", 17, TEXT, True).pack(side="left", padx=(0, 26))
        self.view_buttons: dict[str, tk.Button] = {}
        for key, label in (("overview", "总览"), ("settings", "设置"), ("records", "数据")):
            button = tk.Button(top, text=label, command=lambda name=key: self._show_view(name),
                               bg=BG, fg=MUTED, relief="flat", padx=15, pady=5)
            button.pack(side="left", padx=(0, 4))
            self.view_buttons[key] = button
        self.conn_var = tk.StringVar(value="连接中")
        tk.Label(top, textvariable=self.conn_var, bg=PANEL_ALT, fg=MUTED,
                 font=("Microsoft YaHei UI", 9), padx=10, pady=4).pack(side="right")

        if not self.demo_mode:
            devices = tk.Frame(page, bg=BG)
            devices.pack(fill="x", padx=18, pady=(0, 8))
            self._label(devices, "设备", 10, MUTED).pack(side="left", padx=(0, 10))
            self.port_var = tk.StringVar()
            self.port_combo = ttk.Combobox(devices, textvariable=self.port_var,
                                           state="readonly", width=34)
            self.port_combo.pack(side="left", padx=(0, 8))
            tk.Button(devices, text="刷新", command=self._refresh_ports,
                      bg=PANEL_ALT, fg=TEXT, relief="flat", padx=12).pack(side="left", padx=(0, 8))
            self.connect_button = tk.Button(devices, text="断开连接", command=self._toggle_connection,
                                            bg=PANEL_ALT, fg=TEXT, relief="flat", padx=14)
            self.connect_button.pack(side="left", padx=(0, 8))
            self._refresh_ports()

        self.view_area = tk.Frame(page, bg=BG)
        self.view_area.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        self.views = {name: tk.Frame(self.view_area, bg=BG)
                      for name in ("overview", "settings", "records")}
        content = self.views["overview"]
        content.columnconfigure(0, weight=3, uniform="dashboard")
        content.columnconfigure(1, weight=2, uniform="dashboard")
        content.rowconfigure(0, weight=1)

        left = tk.Frame(content, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        right = tk.Frame(content, bg=BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        water_panel = self._panel(left, "杯中水量")
        water_panel.pack(fill="both", expand=True)
        inner = tk.Frame(water_panel, bg=PANEL)
        inner.pack(fill="both", expand=True)
        display = tk.Frame(inner, bg=PANEL)
        display.pack(expand=True)
        self.water_canvas = tk.Canvas(display, bg=PANEL, width=170, height=240,
                                      highlightthickness=0)
        self.water_canvas.pack(side="left", padx=(0, 12))
        numbers = tk.Frame(display, bg=PANEL)
        numbers.pack(side="left", anchor="n", pady=(24, 0))
        self.water_var = tk.StringVar(value="-- ml")
        tk.Label(numbers, textvariable=self.water_var, bg=PANEL, fg=TEXT,
                 font=("Consolas", 26, "bold")).pack(anchor="w")
        self.water_note = tk.StringVar(value="等待杯垫数据")
        tk.Label(numbers, textvariable=self.water_note, bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 9), wraplength=165,
                 justify="left").pack(anchor="w", pady=(7, 0))
        if self.demo_mode:
            tk.Button(numbers, text="模拟喝水 150 ml", command=lambda: self.feed.simulate_drink(150),
                      bg=PANEL_ALT, fg=TEXT, relief="flat", padx=8, pady=5).pack(anchor="w", pady=12)

        today_panel = self._panel(right, "今日饮水")
        today_panel.pack(fill="x", pady=(0, 8))
        self.today_var = tk.StringVar(value="0 ml")
        self._label(today_panel, "已确认饮水", 10, MUTED).pack(anchor="w")
        tk.Label(today_panel, textvariable=self.today_var, bg=PANEL, fg=ACCENT,
                 font=("Consolas", 24, "bold")).pack(anchor="w")
        self.progress_canvas = tk.Canvas(today_panel, height=12, bg=PANEL,
                                         highlightthickness=0)
        self.progress_canvas.pack(fill="x", pady=(6, 5))
        self.goal_var = tk.StringVar(value="")
        tk.Label(today_panel, textvariable=self.goal_var, bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w")

        schedule = self._panel(right, "提醒计划")
        schedule.pack(fill="x", pady=(0, 8))
        self.next_var = tk.StringVar(value="等待设备")
        tk.Label(schedule, textvariable=self.next_var, bg=PANEL, fg=ALERT,
                 font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w")
        self._label(schedule, "仅在工作时段内开始提醒；已出现的提醒需饮水完成。",
                    9, MUTED, wraplength=230, justify="left").pack(anchor="w", pady=(5, 0))

        settings_view = self.views["settings"]
        settings_view.columnconfigure(0, weight=3, uniform="settings")
        settings_view.columnconfigure(1, weight=2, uniform="settings")
        settings_view.rowconfigure(0, weight=1)
        settings_panel = self._panel(settings_view, "饮水计划")
        settings_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        calibration_panel = self._panel(settings_view, "杯子标定")
        calibration_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self.entries: dict[str, tk.Entry] = {}
        fields = (
            ("work_start", "上班时间", settings.work_start),
            ("work_end", "下班时间", settings.work_end),
            ("interval_min", "喝水间隔（分钟）", settings.interval_min),
            ("sip_target_ml", "每次提醒需喝（ml）", settings.sip_target_ml),
            ("daily_goal_ml", "每日目标（ml）", settings.daily_goal_ml),
            ("cup_capacity_ml", "参考杯容量（未标满杯）", settings.cup_capacity_ml),
        )
        grid = tk.Frame(settings_panel, bg=PANEL)
        grid.pack(fill="x")
        for index, (key, label, value) in enumerate(fields):
            row, col = divmod(index, 2)
            cell = tk.Frame(grid, bg=PANEL)
            cell.grid(row=row, column=col, sticky="ew", padx=(0, 8), pady=2)
            self._label(cell, label, 9, MUTED).pack(anchor="w")
            entry = tk.Entry(cell, bg=PANEL_ALT, fg=TEXT, insertbackground=TEXT,
                             relief="flat", font=("Consolas", 12), width=14)
            entry.insert(0, str(value))
            entry.pack(fill="x", ipady=3)
            self.entries[key] = entry
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        tk.Button(settings_panel, text="保存设置", command=self._save_settings,
                  bg=ACCENT, fg=BG, activebackground=ACCENT, relief="flat",
                  font=("Microsoft YaHei UI", 10, "bold"), pady=5).pack(fill="x", pady=(8, 6))
        self._label(calibration_panel, "先放空杯并记录；再装满水记录满杯重。",
                    9, MUTED, wraplength=340, justify="left").pack(anchor="w", pady=(0, 14))
        self.tare_button = tk.Button(calibration_panel, text="空杯放上后，记录空杯重",
                                     command=self._calibrate_cup,
                                     bg=PANEL_ALT, fg=TEXT, relief="flat", pady=5)
        self.tare_button.pack(fill="x")
        self.full_button = tk.Button(calibration_panel, text="加满水后，记录满杯重",
                                     command=self._calibrate_full,
                                     bg=PANEL_ALT, fg=TEXT, relief="flat", pady=5)
        self.full_button.pack(fill="x", pady=(6, 0))
        self.calibration_mode_var = tk.StringVar(value="")
        tk.Label(calibration_panel, textvariable=self.calibration_mode_var, bg=PANEL,
                 fg=ACCENT, font=("Microsoft YaHei UI", 10, "bold"),
                 anchor="w").pack(fill="x", pady=(22, 6))
        self.action_status = tk.StringVar(value="")
        self.action_status_label = tk.Label(calibration_panel, textvariable=self.action_status,
                                            bg=PANEL, fg=ACCENT,
                                            font=("Microsoft YaHei UI", 9), anchor="w",
                                            justify="left", wraplength=335)
        self.action_status_label.pack(fill="x", pady=(5, 12))
        self.tare_var = tk.StringVar(value="")
        tk.Label(calibration_panel, textvariable=self.tare_var, bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(2, 0))
        self.full_var = tk.StringVar(value="")
        tk.Label(calibration_panel, textvariable=self.full_var, bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(2, 0))

        recent_panel = self._panel(self.views["records"], "饮水记录")
        recent_panel.pack(fill="both", expand=True)
        actions = tk.Frame(recent_panel, bg=PANEL)
        actions.pack(fill="x", pady=(0, 8))
        for label, callback in (("导出 CSV", self._export_records),
                                ("删除选中", self._delete_selected),
                                ("清空今日", lambda: self._clear_records("today")),
                                ("清空全部", lambda: self._clear_records("all"))):
            tk.Button(actions, text=label, command=callback, bg=PANEL_ALT, fg=TEXT,
                      relief="flat", padx=12, pady=5).pack(side="left", padx=(0, 8))
        style = ttk.Style(self)
        style.configure("Coaster.Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, rowheight=26)
        style.configure("Coaster.Treeview.Heading", foreground=BG)
        self.records_tree = ttk.Treeview(recent_panel, columns=("time", "amount", "kind"),
                                         show="headings", selectmode="extended",
                                         style="Coaster.Treeview", height=10)
        for key, title, width in (("time", "时间", 280), ("amount", "饮水量", 180),
                                  ("kind", "类型", 180)):
            self.records_tree.heading(key, text=title)
            self.records_tree.column(key, width=width, anchor="w")
        self.records_tree.pack(fill="both", expand=True)
        self.records_status = tk.StringVar(value="可导出备份，再删除选中的记录或清空统计。")
        tk.Label(recent_panel, textvariable=self.records_status, bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 9), anchor="w").pack(fill="x", pady=(7, 0))
        pager = tk.Frame(recent_panel, bg=PANEL)
        pager.pack(fill="x", pady=(8, 0))
        tk.Button(pager, text="上一页", command=lambda: self._change_records_page(-1),
                  bg=PANEL_ALT, fg=TEXT, relief="flat", padx=10).pack(side="left")
        self.records_page_label = tk.StringVar(value="第 1 页")
        self._label(pager, f"每页 {RECORDS_PAGE_SIZE} 条", 9, MUTED).pack(side="right")
        tk.Button(pager, text="下一页", command=lambda: self._change_records_page(1),
                  bg=PANEL_ALT, fg=TEXT, relief="flat", padx=10).pack(side="right", padx=(0, 8))
        tk.Label(pager, textvariable=self.records_page_label, bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 9)).pack(side="left", padx=12)
        self._show_view("overview")

    def _show_view(self, name: str) -> None:
        if name != "records":
            self.delete_pending = None
        self.active_view = name
        for view in self.views.values():
            view.pack_forget()
        self.views[name].pack(fill="both", expand=True)
        for key, button in self.view_buttons.items():
            button.configure(bg=ACCENT if key == name else BG,
                             fg=BG if key == name else MUTED)
        if name == "records":
            self._refresh_records()

    def _refresh_records(self) -> None:
        self.records_tree.delete(*self.records_tree.get_children())
        rows = self.store.list_drinks(RECORDS_PAGE_SIZE,
                                      self.records_page * RECORDS_PAGE_SIZE)
        for id_, at, ml, estimated in rows:
            self.records_tree.insert("", "end", iid=str(id_), values=(
                datetime.fromisoformat(at).strftime("%Y-%m-%d %H:%M"),
                f"{ml:.0f} ml", "估算" if estimated else "称重确认"))
        self.records_page_label.set(f"第 {self.records_page + 1} 页")
        self.records_dirty = False

    def _change_records_page(self, direction: int) -> None:
        page = max(0, self.records_page + direction)
        if page > self.records_page and not self.store.list_drinks(1, page * RECORDS_PAGE_SIZE):
            return
        self.records_page = page
        self._refresh_records()

    def _export_records(self) -> None:
        path = filedialog.asksaveasfilename(parent=self, title="导出饮水记录",
                                            defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            count = self.store.export_csv(Path(path))
        except OSError as exc:
            self.records_status.set(f"导出失败：{exc}")
            return
        self.records_status.set(f"已导出 {count} 条记录：{Path(path).name}")

    def _confirm_delete(self, action: str, ids: tuple[int, ...], label: str) -> bool:
        pending = self.delete_pending
        if (pending is None or pending[0] != action or pending[2] != ids or
                time.monotonic() - pending[1] > 30):
            self.delete_pending = (action, time.monotonic(), ids)
            self.records_status.set(f"再次点击「{label}」确认；建议先导出 CSV 备份。")
            return False
        self.delete_pending = None
        return True

    def _delete_selected(self) -> None:
        ids = tuple(sorted(int(item) for item in self.records_tree.selection()))
        if not ids:
            self.records_status.set("请先选中要删除的记录。")
            return
        if not self._confirm_delete("selected", ids, "删除选中"):
            return
        count = self.store.delete_drinks(list(ids))
        self.records_status.set(f"已删除 {count} 条记录。")
        self._refresh_records()
        self._render()

    def _clear_records(self, scope: str) -> None:
        label = "清空今日" if scope == "today" else "清空全部"
        if not self._confirm_delete(scope, (), label):
            return
        day = datetime.now().astimezone().date().isoformat() if scope == "today" else None
        count = self.store.clear_drinks(day)
        self.records_page = 0
        self.records_status.set(f"已删除 {count} 条记录。")
        self._refresh_records()
        self._render()

    def _save_settings(self) -> None:
        try:
            old = self.core.settings
            settings = Settings(
                work_start=self.entries["work_start"].get().strip(),
                work_end=self.entries["work_end"].get().strip(),
                interval_min=int(self.entries["interval_min"].get()),
                sip_target_ml=int(self.entries["sip_target_ml"].get()),
                daily_goal_ml=int(self.entries["daily_goal_ml"].get()),
                cup_capacity_ml=int(self.entries["cup_capacity_ml"].get()),
                cup_tare_g=old.cup_tare_g,
                cup_full_g=old.cup_full_g,
            )
            settings.validate()
        except ValueError as exc:
            self._set_action_status(f"设置无效：{exc}", error=True)
            return
        self.store.save_settings(settings)
        self.core.settings = settings
        self._render()
        self._set_action_status("已保存设置")

    def _set_action_status(self, message: str, error: bool = False) -> None:
        self.action_status.set(message)
        self.action_status_label.configure(fg=ALERT if error else ACCENT)

    def _reset_tare_confirmation(self) -> None:
        self.tare_pending = None
        self.tare_button.configure(text="空杯放上后，记录空杯重")

    def _reset_full_confirmation(self) -> None:
        self.full_pending = None
        self.full_button.configure(text="加满水后，记录满杯重")

    def _sync_calibration(self) -> None:
        if (self.core.settings.cup_tare_g is not None and self.feed is not None
                and hasattr(self.feed, "send_command")):
            self.calibration_sync_error = False
            self.feed.send_command({"cmd": "set_cup_calibration",
                                    "empty_g": self.core.settings.cup_tare_g or 0,
                                    "full_g": self.core.settings.cup_full_g or 0})

    def _calibrate_cup(self) -> None:
        if (not self._connected(datetime.now().astimezone()) or
                self.device_state != "stable" or self.weight_g is None or
                not 0 < self.weight_g <= 5000):
            self._reset_tare_confirmation()
            self._set_action_status("请先把空杯放在杯垫上，等待重量稳定。", error=True)
            return
        pending = self.tare_pending
        if (pending is None or time.monotonic() - pending[1] > 30
                or abs(self.weight_g - pending[0]) > 2):
            self.tare_pending = (self.weight_g, time.monotonic())
            self.tare_button.configure(text=f"确认空杯，记录 {self.weight_g:.1f} g")
            self._set_action_status("确认杯子已倒空后，再点击一次记录。")
            return
        self.core.settings.cup_tare_g = round(self.weight_g, 1)
        self.core.settings.cup_full_g = None
        self.store.save_settings(self.core.settings)
        self._reset_tare_confirmation()
        self._reset_full_confirmation()
        self._sync_calibration()
        self._render()
        self._set_action_status(f"已记录空杯重：{self.core.settings.cup_tare_g:.1f} g")

    def _calibrate_full(self) -> None:
        tare = self.core.settings.cup_tare_g
        if (tare is None or not self._connected(datetime.now().astimezone()) or
                self.device_state != "stable" or self.weight_g is None or
                not tare + 50 <= self.weight_g <= 8000):
            self._reset_full_confirmation()
            self._set_action_status("请先记录空杯重，再加满水并等待重量稳定。", error=True)
            return
        pending = self.full_pending
        if (pending is None or time.monotonic() - pending[1] > 30 or
                abs(self.weight_g - pending[0]) > 2):
            self.full_pending = (self.weight_g, time.monotonic())
            self.full_button.configure(text=f"确认满杯，记录 {self.weight_g:.1f} g")
            self._set_action_status("确认杯子已经加满后，再点击一次记录。")
            return
        self.core.settings.cup_full_g = round(self.weight_g, 1)
        self.store.save_settings(self.core.settings)
        self._reset_full_confirmation()
        self._sync_calibration()
        self._render()
        self._set_action_status(f"已记录满杯重：{self.core.settings.cup_full_g:.1f} g")

    def _connected(self, now: datetime) -> bool:
        return (self.connection and self.last_frame_at is not None
                and (now - self.last_frame_at).total_seconds() < 6)

    def _handle_frame(self, frame: dict, now: datetime) -> None:
        if frame.get("ack") == "set_cup_calibration":
            self.calibration_sync_error = not bool(frame.get("ok"))
            if self.calibration_sync_error:
                self._set_action_status("设备未接受杯子标定，请更新固件或检查连接。", error=True)
            return
        config = frame.get("config")
        if isinstance(config, dict) and self.core.settings.cup_tare_g is None:
            empty = config.get("empty_cup_g")
            full = config.get("full_cup_g")
            if isinstance(empty, (int, float)) and empty > 0:
                settings = self.core.settings
                settings.cup_tare_g = float(empty)
                settings.cup_full_g = float(full) if isinstance(full, (int, float)) and full > 0 else None
                try:
                    settings.validate()
                except ValueError:
                    settings.cup_tare_g = settings.cup_full_g = None
                else:
                    self.store.save_settings(settings)
            return
        status = frame.get("status")
        if isinstance(status, dict):
            weight = status.get("weight_g")
            state = status.get("state")
            if isinstance(weight, (int, float)) and math.isfinite(weight) and isinstance(state, str):
                self.weight_g = float(weight)
                self.device_state = state
                self.last_frame_at = now
            return
        if frame.get("event") == "drink":
            amount = frame.get("ml")
            if (not isinstance(amount, (int, float)) or not math.isfinite(amount)
                    or not 0 < amount <= 3000):
                return
            estimated = bool(frame.get("estimated", False))
            self.store.add_drink(now, float(amount), estimated)
            self.records_dirty = True
            was_active = self.core.alert_active
            satisfied = self.core.register_drink(now, float(amount), estimated)
            self._persist_runtime()
            if satisfied:
                self._hide_alert()
            elif was_active:
                self._update_alert()

    def _persist_runtime(self) -> None:
        self.store.save_runtime(self.core.last_qualified, self.core.alert_started,
                                self.core.alert_progress_ml)

    def _refresh_ports(self) -> None:
        selected = self.port_choices.get(self.port_var.get()) if hasattr(self, "port_choices") else None
        if selected is None:
            selected = self.feed.requested_port if self.feed is not None else "auto"
        self.port_choices = {"自动查找 ESP32-C3": "auto"}
        try:
            for port, description in available_ports():
                self.port_choices[f"{port}  {description}"] = port
        except (ImportError, OSError) as exc:
            self.connection_detail = f"读取串口列表失败：{exc}"
        if selected != "auto" and selected not in self.port_choices.values():
            self.port_choices[selected] = selected
        self.port_combo["values"] = list(self.port_choices)
        self.port_var.set(next(label for label, port in self.port_choices.items() if port == selected))

    def _consume_messages(self, now: datetime, include_connection: bool = True,
                          limit: int | None = 200) -> None:
        count = 0
        while limit is None or count < limit:
            try:
                message = self.messages.get_nowait()
            except queue.Empty:
                break
            count += 1
            if message[0] == "connection":
                if include_connection:
                    self.connection = bool(message[1])
                    self.connection_detail = str(message[2])
                    if self.connection:
                        if self.core.settings.cup_tare_g is None and hasattr(self.feed, "send_command"):
                            self.feed.send_command({"cmd": "get_config"})
                        else:
                            self._sync_calibration()
                    if not self.connection:
                        self.last_frame_at = None
            elif message[0] == "frame":
                self._handle_frame(message[1], now)

    def _disconnect(self) -> None:
        if self.demo_mode:
            return
        if self.feed is not None:
            self.feed.stop()
            self._consume_messages(datetime.now().astimezone(), include_connection=False, limit=None)
            self.feed = None
        self.connection = False
        self.connection_detail = "已断开"
        self.calibration_sync_error = False
        self.last_frame_at = None
        self.weight_g = None
        self.device_state = "unknown"
        self._render()

    def _toggle_connection(self) -> None:
        if self.feed is None:
            self._connect_selected()
        else:
            self._disconnect()

    def _connect_selected(self) -> None:
        if self.demo_mode:
            return
        selected = self.port_choices.get(self.port_var.get())
        if selected is None:
            return
        self._disconnect()
        self.connection_detail = "连接中"
        self.feed = SerialFeed(selected, self.messages)
        self.feed.start()
        self._render()

    def _tick(self) -> None:
        if self._closing:
            return
        now = datetime.now().astimezone()
        try:
            self._consume_messages(now)
            if self.core.tick(now, self._connected(now)):
                self._persist_runtime()
            if self.core.alert_active:
                self._show_alert()
            self._render()
        finally:
            if not self._closing:
                self._schedule_tick(500)

    def _render(self) -> None:
        now = datetime.now().astimezone()
        connected = self._connected(now)
        detail = (f"{self.connection_detail} · 标定未同步" if connected and self.calibration_sync_error
                  else self.connection_detail)
        self.conn_var.set(f"● {detail}" if connected else f"● {detail[:42]}")
        if not self.demo_mode:
            self.connect_button.configure(text="连接设备" if self.feed is None else "断开连接",
                                          bg=ACCENT if self.feed is None else PANEL_ALT,
                                          fg=BG if self.feed is None else TEXT)
        self.tare_var.set(f"空杯重：{self.core.settings.cup_tare_g:.1f} g" if self.core.settings.cup_tare_g is not None
                          else "尚未记录空杯重")
        self.calibration_mode_var.set("空杯 + 满杯标定" if self.core.settings.cup_full_g is not None
                                      else "仅空杯标定" if self.core.settings.cup_tare_g is not None
                                      else "尚未标定杯子")
        self.full_var.set(f"满杯重：{self.core.settings.cup_full_g:.1f} g · 容量 {self.core.settings.calibrated_capacity_ml:.0f} ml"
                          if self.core.settings.cup_full_g is not None else "尚未记录满杯重：仅按净重量差统计")
        water = self.core.water_ml(self.weight_g, self.device_state) if connected else None
        if water is not None:
            self.water_var.set(f"{water:.0f} ml")
            capacity = self.core.settings.calibrated_capacity_ml or self.core.settings.cup_capacity_ml
            if (self.core.settings.cup_full_g is not None and self.weight_g is not None
                    and self.weight_g > self.core.settings.cup_full_g + 4):
                self.water_note.set("当前重量超过满杯标定，请检查杯子或重新标定。")
            else:
                self.water_note.set(f"杯中估算水量 · 参考容量 {capacity:.0f} ml")
        elif connected and self.device_state == "stable" and self.weight_g is not None:
            self.water_var.set(f"{self.weight_g:.1f} g")
            self.water_note.set("杯+水总重。请将空杯放上并记录空杯重，之后才能显示水量。")
        elif not connected:
            self.water_var.set("-- ml")
            self.water_note.set("等待杯垫连接")
        elif self.device_state == "no_cup":
            self.water_var.set("-- ml")
            self.water_note.set("杯垫上暂未检测到杯子")
        else:
            self.water_var.set("-- ml")
            self.water_note.set("正在等待杯子重量稳定")
        self._draw_water(water, connected and self.device_state == "stable")

        confirmed, estimated = self.store.today_totals(now)
        self.today_var.set(f"{confirmed:.0f} ml")
        self.goal_var.set(f"每日目标 {self.core.settings.daily_goal_ml} ml · 达成 {confirmed / self.core.settings.daily_goal_ml:.0%}"
                          + (f" · 另有估算 {estimated:.0f} ml" if estimated else ""))
        self._draw_progress(min(1.0, confirmed / self.core.settings.daily_goal_ml))
        if self.core.alert_active:
            remaining = max(0, self.core.settings.sip_target_ml - self.core.alert_progress_ml)
            self.next_var.set(f"提醒中 · 还需 {remaining:.0f} ml")
        elif not connected:
            self.next_var.set("等待杯垫连接")
        else:
            due = self.core.due_at(now)
            self.next_var.set(f"下次提醒 {due:%H:%M}" if due else "工作时段外")
        if self.active_view == "records" and self.records_dirty:
            self._refresh_records()

    def _draw_water(self, water: float | None, cup_present: bool) -> None:
        canvas = self.water_canvas
        canvas.delete("all")
        canvas.create_rectangle(28, 18, 125, 205, outline=WATER, width=4)
        canvas.create_line(25, 17, 128, 17, fill=WATER, width=5)
        canvas.create_arc(114, 55, 168, 160, start=270, extent=180,
                          style="arc", outline=WATER, width=4)
        if water is not None:
            capacity = self.core.settings.calibrated_capacity_ml or self.core.settings.cup_capacity_ml
            ratio = min(1.0, water / capacity)
            top = 201 - ratio * 179
            if ratio > 0:
                canvas.create_rectangle(32, top, 121, 201, fill=WATER, outline="")
        elif cup_present:
            canvas.create_text(76, 111, text="已放杯", fill=ACCENT,
                               font=("Microsoft YaHei UI", 12, "bold"))
        canvas.create_text(76, 225, text="估算液位" if water is not None else "杯子状态", fill=MUTED,
                           font=("Microsoft YaHei UI", 9))

    def _draw_progress(self, ratio: float) -> None:
        canvas = self.progress_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 100)
        canvas.create_rectangle(0, 2, width, 10, fill=PANEL_ALT, outline="")
        if ratio > 0:
            canvas.create_rectangle(0, 2, width * ratio, 10, fill=ACCENT, outline="")

    def _show_alert(self) -> None:
        if self.alert_window is not None:
            self._update_alert()
            return
        window = tk.Toplevel(self)
        self.alert_window = window
        window.configure(bg=BG)
        window.attributes("-fullscreen", True)
        window.attributes("-topmost", True)
        window.protocol("WM_DELETE_WINDOW", lambda: None)
        window.bind("<Escape>", lambda _event: "break")
        window.bind("<Alt-F4>", lambda _event: "break")
        window.bind("<Control-Shift-Q>", self._emergency_exit)
        window.grab_set()
        body = tk.Frame(window, bg=BG)
        body.place(relx=0.5, rely=0.5, anchor="center")
        title = ("上次提醒尚未完成" if self.core.alert_started == self._restored_alert_started
                 else "现在喝水。")
        self._label(body, title, 48, TEXT, True).pack(pady=(0, 20))
        self.alert_text = tk.StringVar()
        tk.Label(body, textvariable=self.alert_text, bg=BG, fg=ACCENT,
                 font=("Microsoft YaHei UI", 22)).pack(pady=(0, 24))
        self._label(body, "拿起杯子喝水，放回杯垫后会自动解除提醒。",
                    15, MUTED).pack()
        if self.demo_mode:
            tk.Button(body, text="模拟喝水", command=lambda: self.feed.simulate_drink(self.core.settings.sip_target_ml),
                      bg=ACCENT, fg=BG, relief="flat", padx=26, pady=10).pack(pady=25)
        self._label(body, "紧急关闭整个软件：Ctrl + Shift + Q", 10, MUTED).pack(pady=(50, 0))
        self._update_alert()

    def _update_alert(self) -> None:
        if self.alert_window is None:
            return
        remaining = max(0, self.core.settings.sip_target_ml - self.core.alert_progress_ml)
        self.alert_text.set(f"还需确认饮水 {remaining:.0f} ml")
        self.alert_window.lift()
        self.alert_window.focus_force()

    def _hide_alert(self) -> None:
        if self.alert_window is not None:
            try:
                self.alert_window.grab_release()
            except tk.TclError:
                pass
            self.alert_window.destroy()
            self.alert_window = None

    def _on_close(self) -> None:
        if self.core.alert_active:
            self._show_alert()
            return
        self._shutdown()

    def _emergency_exit(self, _event=None) -> str:
        self._shutdown()
        return "break"

    def _shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        for job in self._tick_jobs:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._tick_jobs.clear()
        self._hide_alert()
        if self.feed is not None:
            self.feed.stop()
        self.store.close()
        self.destroy()
