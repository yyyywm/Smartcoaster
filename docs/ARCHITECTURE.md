# 架构与数据边界

## 数据流

```text
HX711 → 固件状态机 → USB JSON Lines → SerialFeed → 消息队列
                                                  ↓
                                       Tk 主线程 App
                                        ↓         ↓
                                HydrationCore   Store / SQLite
                                        ↓         ↓
                                    全屏提醒    总览、月历、记录
```

固件负责稳定称重、净变化识别和 NVS；桌面端负责按本机时间提醒、按本机日期记账和展示。两侧各有提醒状态，桌面端不会直接使用固件的 `remind` 事件触发全屏提示。

## 桌面端模块

| 文件 | 职责 |
|---|---|
| `desktop/smart_coaster.py` | 参数解析、存储与应用生命周期 |
| `coaster_app/model.py` | 设置校验、工作时段、提醒/稍后提醒和杯中水量 |
| `coaster_app/storage.py` | SQLite 设置、运行状态、记录、月汇总和 CSV |
| `coaster_app/transport.py` | 串口线程、自动重连、命令队列和演示源 |
| `coaster_app/ui.py` | Tk 主线程、页面、标定和提醒窗口 |
| `coaster_app/calendar_view.py` | 周一开始的自适应月历绘制 |
| `coaster_app/reminder_image.py` | 背景导入、尺寸限制与适配 |
| `coaster_app/displays.py` / `dpi.py` | 显示器边界和 DPI |
| `soft_button.py` / `rounded_panel.py` / `water_view.py` | 界面组件与动画 |
| `tray.py` | 托盘线程与主线程消息桥接 |

除入口外，上述 Python 文件均位于 `desktop/coaster_app/`。串口和托盘线程通过队列通知 Tk 线程，不直接操作 Tk 控件或 SQLite 连接。

## 本地持久化

默认目录：Windows 为 `%LOCALAPPDATA%\SmartCoaster`，其他系统为 `~/.local/share/SmartCoaster`。通过 `--db 路径` 可指定独立数据库；相对路径按启动工作目录解释。

- `kv(key, value)`：JSON 格式设置、上次达标时间等运行状态。
- `drinks(id, at, day, ml, estimated)`：记录时间、采集时本机日期、毫升数及旧估算标志。
- `reminder_images/`：数据库旁的用户背景图片副本。

`day` 在新增记录时确定，不按 UTC 重分组。今日总量和月历只计入 `estimated=0`。月度查询按日期范围直接聚合，不受数据页分页或历史查询上限影响。

当前不保存每日目标历史。修改目标后，过去日期也按当前目标重新判断。没有确认记录的日期显示灰色，不自动视为 0 ml 未达标；未来日期始终灰色。统计页打开时，以及记录、目标或本机日期变化后更新。

删除记录不改变标定，也不回算先前已触发的提醒状态。CSV 是饮水记录导出，不是包含设置和图片的完整恢复包。

## 固件模块

- `components/hx711/`：GPIO 时钟和数据读取、超时；不是硬件 SPI。
- `components/coaster/coaster.c`：无杯、稳定中、稳定状态及净变化判定。
- `components/coaster/storage.c`：配置、零点和稳定参考写入 NVS。
- `components/coaster/protocol.c`：协议发送和按行接收。
- `main/coaster_main.c`：采样、共享状态保护、事件分发和命令处理。

`session_ml` 只代表本次上电累计，不替代逐日记录。拿杯期间喝水又加水无法从两次称重反推实际饮水量；补水只重置桌面端提醒计时，不增加日/月累计。

## CAD

原生模型与装配保留在同一目录，避免破坏相对引用。当前装配是布局检查用，尚无完整螺钉、电子板和装配约束；STL 不替代原生模型。
