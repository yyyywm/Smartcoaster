"""Tkinter dashboard and fullscreen drinking reminder."""
from __future__ import annotations

from datetime import datetime
import math
import queue

from .dpi import enable_native_dpi

enable_native_dpi()

import tkinter as tk
from tkinter import messagebox, ttk

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
        self.weight_g: float | None = None
        self.device_state = "unknown"
        self.connection = False
        self.connection_detail = "连接中"
        self.last_frame_at: datetime | None = None
        self.alert_window: tk.Toplevel | None = None
        self._closing = False
        self._tick_jobs: list[str] = []

        self.title("智能杯垫 · 饮水提醒")
        self.configure(bg=BG)
        width = min(1400, self.winfo_screenwidth() - 80)
        height = min(860, self.winfo_screenheight() - 120)
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
        panel = tk.Frame(parent, bg=PANEL, padx=22, pady=12,
                         highlightthickness=1, highlightbackground="#31424A")
        self._label(panel, title, 11, MUTED, True).pack(anchor="w", pady=(0, 10))
        return panel

    def _build(self) -> None:
        settings = self.core.settings
        viewport = tk.Canvas(self, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(self, orient="vertical", command=viewport.yview)
        viewport.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        viewport.pack(side="left", fill="both", expand=True)
        page = tk.Frame(viewport, bg=BG)
        page_id = viewport.create_window(0, 0, window=page, anchor="nw")
        page.bind("<Configure>", lambda _event: viewport.configure(scrollregion=viewport.bbox("all")))
        viewport.bind("<Configure>", lambda event: viewport.itemconfigure(page_id, width=event.width))

        top = tk.Frame(page, bg=BG)
        top.pack(fill="x", padx=30, pady=(14, 8))
        self._label(top, "喝水，别等到口渴。", 23, TEXT, True).pack(side="left")
        self.conn_var = tk.StringVar(value="连接中")
        tk.Label(top, textvariable=self.conn_var, bg=PANEL_ALT, fg=MUTED,
                 font=("Microsoft YaHei UI", 10), padx=12, pady=7).pack(side="right")

        if not self.demo_mode:
            devices = tk.Frame(page, bg=BG)
            devices.pack(fill="x", padx=30, pady=(0, 12))
            self._label(devices, "连接设备", 10, MUTED).pack(side="left", padx=(0, 10))
            self.port_var = tk.StringVar()
            self.port_combo = ttk.Combobox(devices, textvariable=self.port_var,
                                           state="readonly", width=38)
            self.port_combo.pack(side="left", padx=(0, 8))
            tk.Button(devices, text="刷新", command=self._refresh_ports,
                      bg=PANEL_ALT, fg=TEXT, relief="flat", padx=12).pack(side="left", padx=(0, 8))
            tk.Button(devices, text="连接", command=self._connect_selected,
                      bg=ACCENT, fg=BG, relief="flat", padx=14).pack(side="left", padx=(0, 8))
            tk.Button(devices, text="断开", command=self._disconnect,
                      bg=PANEL_ALT, fg=TEXT, relief="flat", padx=14).pack(side="left")
            self._refresh_ports()

        content = tk.Frame(page, bg=BG)
        content.pack(fill="both", expand=True, padx=24)
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(0, weight=1)

        left = tk.Frame(content, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = tk.Frame(content, bg=BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        water_panel = self._panel(left, "杯中水量")
        water_panel.pack(fill="both", expand=True, pady=(0, 8))
        inner = tk.Frame(water_panel, bg=PANEL)
        inner.pack(fill="both", expand=True)
        self.water_canvas = tk.Canvas(inner, bg=PANEL, width=210, height=265,
                                      highlightthickness=0)
        self.water_canvas.pack(side="left", padx=(6, 24))
        numbers = tk.Frame(inner, bg=PANEL)
        numbers.pack(side="left", fill="both", expand=True, pady=36)
        self.water_var = tk.StringVar(value="-- ml")
        tk.Label(numbers, textvariable=self.water_var, bg=PANEL, fg=TEXT,
                 font=("Consolas", 32, "bold")).pack(anchor="w")
        self.water_note = tk.StringVar(value="等待杯垫数据")
        tk.Label(numbers, textvariable=self.water_note, bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 10), wraplength=240,
                 justify="left").pack(anchor="w", pady=(10, 0))
        if self.demo_mode:
            tk.Button(numbers, text="模拟喝水 150 ml", command=lambda: self.feed.simulate_drink(150),
                      bg=PANEL_ALT, fg=TEXT, relief="flat", padx=12, pady=8).pack(anchor="w", pady=20)

        today_panel = self._panel(left, "今日饮水")
        today_panel.pack(fill="x")
        self.today_var = tk.StringVar(value="0 ml")
        self._label(today_panel, "已确认饮水", 10, MUTED).pack(anchor="w")
        tk.Label(today_panel, textvariable=self.today_var, bg=PANEL, fg=ACCENT,
                 font=("Consolas", 28, "bold")).pack(anchor="w")
        self.progress_canvas = tk.Canvas(today_panel, height=16, bg=PANEL,
                                         highlightthickness=0)
        self.progress_canvas.pack(fill="x", pady=(10, 8))
        self.goal_var = tk.StringVar(value="")
        tk.Label(today_panel, textvariable=self.goal_var, bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w")

        schedule = self._panel(right, "提醒计划")
        schedule.pack(fill="x", pady=(0, 8))
        self.next_var = tk.StringVar(value="等待设备")
        tk.Label(schedule, textvariable=self.next_var, bg=PANEL, fg=ALERT,
                 font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w")
        self._label(schedule, "仅在工作时段内开始提醒；已出现的提醒需饮水完成。",
                    9, MUTED, wraplength=340, justify="left").pack(anchor="w", pady=(8, 0))

        settings_panel = self._panel(right, "个人设置")
        settings_panel.pack(fill="both", expand=True, pady=(0, 8))
        self.entries: dict[str, tk.Entry] = {}
        fields = (
            ("work_start", "上班时间", settings.work_start),
            ("work_end", "下班时间", settings.work_end),
            ("interval_min", "喝水间隔（分钟）", settings.interval_min),
            ("sip_target_ml", "每次提醒需喝（ml）", settings.sip_target_ml),
            ("daily_goal_ml", "每日目标（ml）", settings.daily_goal_ml),
            ("cup_capacity_ml", "杯子容量（ml）", settings.cup_capacity_ml),
        )
        grid = tk.Frame(settings_panel, bg=PANEL)
        grid.pack(fill="x")
        for index, (key, label, value) in enumerate(fields):
            row, col = divmod(index, 2)
            cell = tk.Frame(grid, bg=PANEL)
            cell.grid(row=row, column=col, sticky="ew", padx=(0, 12), pady=4)
            self._label(cell, label, 9, MUTED).pack(anchor="w")
            entry = tk.Entry(cell, bg=PANEL_ALT, fg=TEXT, insertbackground=TEXT,
                             relief="flat", font=("Consolas", 12), width=14)
            entry.insert(0, str(value))
            entry.pack(fill="x", ipady=6)
            self.entries[key] = entry
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        tk.Button(settings_panel, text="保存设置", command=self._save_settings,
                  bg=ACCENT, fg=BG, activebackground=ACCENT, relief="flat",
                  font=("Microsoft YaHei UI", 10, "bold"), pady=8).pack(fill="x", pady=(12, 8))
        tk.Button(settings_panel, text="空杯放上后，记录空杯重", command=self._calibrate_cup,
                  bg=PANEL_ALT, fg=TEXT, relief="flat", pady=7).pack(fill="x")
        self.tare_var = tk.StringVar(value="")
        tk.Label(settings_panel, textvariable=self.tare_var, bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(8, 0))

        recent_panel = self._panel(right, "最近饮水")
        recent_panel.pack(fill="x")
        self.recent_var = tk.StringVar(value="暂无记录")
        tk.Label(recent_panel, textvariable=self.recent_var, bg=PANEL, fg=MUTED,
                 font=("Consolas", 10), justify="left", anchor="w").pack(fill="x")

        footer = tk.Frame(page, bg=BG)
        footer.pack(fill="x", padx=30, pady=(4, 8))
        self._label(footer, "饮水量按固件确认的重量差统计；水量需先记录空杯重。",
                    9, MUTED).pack(side="left")
        self._label(footer, "紧急退出：Ctrl + Shift + Q", 9, MUTED).pack(side="right")

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
            )
            settings.validate()
        except ValueError as exc:
            messagebox.showerror("设置无效", str(exc), parent=self)
            return
        self.store.save_settings(settings)
        self.core.settings = settings
        self._render()
        messagebox.showinfo("已保存", "设置已保存到本机。", parent=self)

    def _calibrate_cup(self) -> None:
        if (not self._connected(datetime.now().astimezone()) or
                self.device_state != "stable" or self.weight_g is None or self.weight_g <= 0):
            messagebox.showwarning("无法记录", "请先把空杯放在杯垫上，等待重量稳定。", parent=self)
            return
        if not messagebox.askyesno("记录空杯重", f"确认杯子已倒空？当前总重 {self.weight_g:.1f} g。",
                                   parent=self):
            return
        self.core.settings.cup_tare_g = round(self.weight_g, 1)
        self.store.save_settings(self.core.settings)
        self._render()

    def _connected(self, now: datetime) -> bool:
        return (self.connection and self.last_frame_at is not None
                and (now - self.last_frame_at).total_seconds() < 6)

    def _handle_frame(self, frame: dict, now: datetime) -> None:
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
        self.last_frame_at = None
        self.weight_g = None
        self.device_state = "unknown"
        self._render()

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
        self.conn_var.set(f"● {self.connection_detail}" if connected else f"● {self.connection_detail[:65]}")
        self.tare_var.set(f"空杯重：{self.core.settings.cup_tare_g:.1f} g" if self.core.settings.cup_tare_g is not None
                          else "尚未记录空杯重")
        water = self.core.water_ml(self.weight_g, self.device_state) if connected else None
        if water is not None:
            self.water_var.set(f"{water:.0f} ml")
            self.water_note.set(f"估算剩余水量 · 杯子容量 {self.core.settings.cup_capacity_ml} ml")
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
        recent = self.store.recent(5)
        self.recent_var.set("\n".join(
            f"{datetime.fromisoformat(at):%m-%d %H:%M}   {ml:.0f} ml" + (" 估算" if est else "")
            for at, ml, est in recent) if recent else "暂无记录")

    def _draw_water(self, water: float | None, cup_present: bool) -> None:
        canvas = self.water_canvas
        canvas.delete("all")
        canvas.create_rectangle(43, 24, 168, 235, outline=WATER, width=4)
        canvas.create_line(39, 23, 172, 23, fill=WATER, width=5)
        canvas.create_arc(153, 65, 217, 184, start=270, extent=180,
                          style="arc", outline=WATER, width=4)
        if water is not None:
            ratio = min(1.0, water / self.core.settings.cup_capacity_ml)
            top = 230 - ratio * 200
            if ratio > 0:
                canvas.create_rectangle(48, top, 163, 230, fill=WATER, outline="")
        elif cup_present:
            canvas.create_text(105, 130, text="已放杯", fill=ACCENT,
                               font=("Microsoft YaHei UI", 12, "bold"))
        canvas.create_text(105, 252, text="估算液位" if water is not None else "杯子状态", fill=MUTED,
                           font=("Microsoft YaHei UI", 9))

    def _draw_progress(self, ratio: float) -> None:
        canvas = self.progress_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 100)
        canvas.create_rectangle(0, 2, width, 14, fill=PANEL_ALT, outline="")
        if ratio > 0:
            canvas.create_rectangle(0, 2, width * ratio, 14, fill=ACCENT, outline="")

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
        self._label(body, "现在喝水。", 48, TEXT, True).pack(pady=(0, 20))
        self.alert_text = tk.StringVar()
        tk.Label(body, textvariable=self.alert_text, bg=BG, fg=ACCENT,
                 font=("Microsoft YaHei UI", 22)).pack(pady=(0, 24))
        self._label(body, "拿起杯子喝水，放回杯垫后会自动解除提醒。",
                    15, MUTED).pack()
        if self.demo_mode:
            tk.Button(body, text="模拟喝水", command=lambda: self.feed.simulate_drink(self.core.settings.sip_target_ml),
                      bg=ACCENT, fg=BG, relief="flat", padx=26, pady=10).pack(pady=25)
        self._label(body, "紧急退出：Ctrl + Shift + Q", 10, MUTED).pack(pady=(50, 0))
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
