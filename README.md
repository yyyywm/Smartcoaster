# 智能杯垫（Smart Coaster）— ESP32-C3 + HX711

基于 ESP32-C3 和 HX711 称重传感器的智能杯垫固件：

- **差值法统计喝水量**：喝水必拿起杯子，杯垫按「拿起前稳定重量 − 放回后稳定重量」结算，无需知道绝对零点
- **喝水提醒**：距上次喝水超过阈值（默认 45 分钟，上位机可配）上报提醒事件
- **零校准设计**：空载基线、空杯重全部自学习，断电存 NVS，上电无缝续接（杯子上电也在杯垫上也无妨）
- **USB 直连上位机**：USB Serial/JTAG（GPIO18/19）上跑 JSON Lines 协议，一根 USB 线供电 + 通信

## 接线

| HX711 | ESP32-C3 |
|---|---|
| DOUT (DT) | GPIO4 |
| SCK | GPIO5 |
| VCC | 3.3V |
| GND | GND |

## 构建烧录

```powershell
& C:\Users\19693\esp\esp-idf\export.ps1
cd firmware
idf.py -p COM18 build flash
```

监视输出：任意串口工具打开 *USB JTAG/serial debug unit (COMx)*，115200 8N1（USB CDC 实际与波特率无关）。

## 单元测试（无需硬件 / IDF）

核心逻辑（状态机 `coaster.c` + 协议格式 `protocol.c`）可脱离 ESP-IDF 在 PC 上直接编译运行，
用于改逻辑/改协议前先自检：

```powershell
cd firmware/tests
make test        # 或 make test CC=gcc
```

详见 [firmware/tests/README.md](firmware/tests/README.md)。

## 上位机软件（桌面端 · Tkinter）

USB 串口接收固件 JSON Lines，桌面端提供工作时段全屏饮水提醒、杯中估算水量、
本机 SQLite 每日统计。提醒设置保存在上位机；杯中水量首次使用须记录空杯重。

```powershell
conda create -y -n dsh_coaster python=3.11
conda activate dsh_coaster
pip install -r host/requirements.txt   # pyserial
python host/smart_coaster.py --simulate    # 无板演示
python host/smart_coaster.py --list        # 查看端口
python host/smart_coaster.py              # 自动连接 ESP32-C3
python host/smart_coaster.py --port COM18  # 或指定端口
```

详见 [host/README.md](host/README.md)。

## ⚠️ 本地 IDF 补丁记录（重要）

本项目将控制台设为 USB Serial/JTAG 主控制台，会触发 ESP-IDF ≤ v5.3.1 的一个官方 bug（[乐鑫通告 AR2025-006](https://documentation.espressif.com/AR2025-006_Usage_Instructions_for_Configuring_the_Console_Output_Channel_for_the_ESP32-C3_Chip_Revision_v1.1.html)）：`esp32c3/clk.c` 中 `esp_rom_uart_tx_wait_idle(CONFIG_ESP_CONSOLE_UART_NUM)` 在 USJ 控制台下传入 -1 导致启动崩溃循环。

已对本地 IDF（`C:\Users\19693\esp\esp-idf`）打补丁（2026-11-07，`git diff` 可见，未提交）：

- `components/esp_system/port/soc/esp32c3/clk.c`：该行外加 `#if CONFIG_ESP_CONSOLE_UART` 保护

官方修复在 **v5.3.2**（commit `3e700ef`）。**升级 IDF 到 v5.3.2 或更高版本后，此本地补丁应丢弃**（`git checkout -- components/esp_system/port/soc/esp32c3/clk.c`）。

## 通信协议（JSON Lines）

设备 → PC（每行一条，上位机按 `{` 开头过滤，其余为调试日志）：

```json
{"event":"cup_placed","weight_g":350.2}
{"event":"cup_removed","weight_g":350.2}
{"event":"drink","ml":148.0,"estimated":0,"weight_g":202.2}
{"event":"refill","ml":210.5,"weight_g":412.7}
{"event":"remind","since_drink_min":46}
{"status":{"weight_g":350.2,"state":"stable","session_ml":450.0,"since_drink_min":3}}
{"ack":"set_reminder","ok":1}
{"config":{"scale":384.70,"reminder_min":45,"estimate_on_refill":1,"baseline_raw":845123,"min_cup_g":215.0}}
```

PC → 设备（每行一条，`\n` 结尾）：

```json
{"cmd":"set_reminder","minutes":45}     // 设置提醒间隔（分钟，0=关闭）
{"cmd":"set_scale","value":384.7}       // 设置称重校准系数（每克码值）
{"cmd":"estimate_on_refill","value":true}  // 续杯时是否按"已喝光"估算喝水量
{"cmd":"calibrate_empty"}               // 仅在无杯状态接受，手动校准基线
{"cmd":"get_config"}                    // 查询当前配置
```

## 工作原理

```
NO_CUP --放杯(>25g连续0.3s)--> SETTLING --窗口1s内极差<4g--> STABLE(结算)
STABLE --拿起(<25g连续0.3s)--> NO_CUP，emit cup_removed
STABLE --在位重量迁移(水壶加水/吸管喝)--> SETTLING --> STABLE(结算)
结算规则：W上次稳定 − W本次稳定 > 5g → drink；< −15g → refill（并按"已喝光"估算补记 drink）
```

- 空载基线：`NO_CUP` 状态下自动慢速跟漂（温漂补偿），发现更低空载点快速学习
- 空杯重：历史最小稳定带杯重量，用于续杯场景估算"喝光"的喝水量
- 状态持久化：每次稳定结算后写入 NVS（包括未达记账阈值的安静结算）；配置变更另行持久化

## 目录结构

```
├── firmware/
│   ├── components/
│   │   ├── hx711/      HX711 驱动（GPIO 位操作 + esp_timer 超时）
│   │   └── coaster/    杯垫核心：状态机(coaster.c) + NVS(storage.c) + 协议(protocol.c)
│   ├── main/
│   │   └── coaster_main.c  主程序：HX711 采样 ~10Hz → 状态机 → JSON 上报
│   └── tests/         宿主侧单元测试（无需 IDF/硬件）：状态机 + 协议格式
└── host/              桌面端上位机：提醒规则 + SQLite + 串口 + Tk 界面
```
