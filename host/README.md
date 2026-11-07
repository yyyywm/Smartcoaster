# 智能杯垫 · 上位机（桌面端，Tkinter）

USB 串口接收 ESP32-C3 杯垫固件发来的 JSON Lines，在**本机桌面窗口**实时显示
重量 / 状态 / 喝水量 / 提醒，并可下发配置命令。

- 框架：Python 标准库 `tkinter`（8.6+）
- 依赖：`pyserial`（仅此一个第三方库）
- 实现要点：串口读写放在后台线程，UI 线程只从队列取数，界面不卡顿
- 无板演示：内置模拟器（`--simulate`），使用与固件相同的 JSON 字段
- 模拟器也响应配置命令，便于检查界面交互；称重系数不会改变模拟重量

## 环境

```powershell
conda create -y -n dsh_coaster python=3.11
conda activate dsh_coaster
pip install -r requirements.txt     # 安装 pyserial
```

> 也可用任意已有 Python 3.10+ 环境，只要 `pip install pyserial` 即可运行。

## 运行

```powershell
# 1) 无板：模拟器
python smart_coaster.py

# 2) 连真机：先 --list 找端口
python smart_coaster.py --list
python smart_coaster.py --port COM18

# 3) 可选
python smart_coaster.py --port COM18 --baud 115200   # 波特率（USB CDC 实际忽略）
python smart_coaster.py --simulate --selftest 15     # 无界面自检（15 秒）
python smart_coaster.py --logic-test                 # 只跑协议/命令逻辑自检
```

## 界面说明

| 区域 | 内容 |
|---|---|
| 顶部 | 模式（模拟器/真机/错误）与连接状态 |
| 左·实时称重 | 杯垫水位绘管 + 重量 + 状态、距提醒剩余、进度条 |
| 左·统计 | 本次饮水 ml、距上次喝水 min、提醒阈值 min |
| 右·配置下发 | 提醒间隔、scale 系数、续杯估算开关、空载校准、读取配置 |
| 右·命令结果 | 下发命令的 ack 回包 |
| 底部 | 事件流（drink / refill / remind / cup_placed / cup_removed） |

## 命令与协议

上位机 → 固件（下行）：`{"cmd":"...","...":...}`，见根目录
`README.md` 协议章节。支持：

| cmd | 载荷 | 说明 |
|---|---|---|
| `set_reminder` | `minutes` (int ≥0) | 喝水提醒间隔，0=关闭 |
| `set_scale` | `value` (>0) | 称重系数 counts/g |
| `estimate_on_refill` | `value` (bool) | 续杯时是否按“已喝光”估算 |
| `calibrate_empty` | — | 空载校准（须先拿空杯） |
| `get_config` | — | 回读配置 |

固件 → 上位机（上行）：`status` / `event` / `config` / `ack` 四种 JSON Lines。

> 注：firmware 目前只实现 set_reminder / set_scale / estimate_on_refill /
> calibrate_empty / get_config 命令；`reset_session` 等无对应实现的命令会
> 被固件回 `ack(ok=false)`。

## 自检

```powershell
python smart_coaster.py --logic-test        # 协议/命令断言
python smart_coaster.py --simulate --selftest 15   # 模拟 15 s + 逻辑自检
python smart_coaster.py --port COM18 --selftest 12 # 真机 12 s（可看到真实重量）
```

`--selftest` 会校验连接与重量上报；模拟器还会校验事件上报。

## 已知限制

- `--port` 打开失败时会抛 `SerialException`（例如串口被其它软件占用），退出码 1。
- 事件去抖/结算逻辑仍在固件侧；上位机只做展示与命令下发，不做二次算法。
- 上位机不保存历史，断开即清空（如需长期记录可后续加 CSV/SQLite 落盘）。

## 目录

- `smart_coaster.py`：上位机主程序（串口/模拟 + UI + 协议）
- `requirements.txt`：依赖清单
- `README.md`：本文件
