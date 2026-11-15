# USB 串口协议

本文对应 `firmware/components/coaster/include/protocol.h`、`protocol.c`、`main/coaster_main.c` 和 `desktop/coaster_app/transport.py`。

## 传输

ESP32-C3 原生 USB Serial/JTAG，GPIO18/19 用于 USB。桌面端按 115200 打开串口；USB CDC 实际传输速率不由该值决定。每条消息为 UTF-8 JSON 对象，以换行结束。ESP 日志可混排，上位机过滤非 JSON 行。串口监视器与桌面端不能同时占用设备。

## 固件到桌面端

```json
{"event":"cup_placed","weight_g":350.2}
{"event":"cup_removed","weight_g":350.2}
{"event":"drink","ml":148.0,"estimated":0,"weight_g":202.2}
{"event":"refill","ml":210.5,"weight_g":412.7}
{"event":"remind","since_drink_min":46}
{"status":{"weight_g":350.2,"state":"stable","session_ml":450.0,"since_drink_min":3}}
{"ack":"set_reminder","ok":1}
{"config":{"scale":384.70,"reminder_min":45,"estimate_on_refill":0,"baseline_raw":845123,"min_cup_g":215.0,"empty_cup_g":120.0,"full_cup_g":620.0}}
```

| 字段/事件 | 含义 |
|---|---|
| `weight_g` | 空载基线以上的杯和水总重，不能直接当作 ml |
| `state` | `no_cup`、`settling`、`stable` |
| `drink.ml` | 可确认净减少，约按 1 g ≈ 1 ml |
| `estimated` | 旧兼容字段，新固件不再从补水推算饮水 |
| `refill.ml` | 可确认净增加，不计饮水总量 |
| `session_ml` | 本次上电累计，不是当天累计 |
| `since_drink_min` | 固件计时，桌面端有独立提醒规则 |
| `ack.ok` | 命令成功为 1，失败为 0 |

桌面端在有效 `drink` 事件到达时追加记录。`status` 不补记事件；离线期间事件没有重放协议。

## 桌面端到固件

```json
{"cmd":"set_reminder","minutes":45}
{"cmd":"set_scale","value":384.7}
{"cmd":"set_cup_calibration","empty_g":120.0,"full_g":620.0}
{"cmd":"calibrate_empty"}
{"cmd":"get_config"}
```

- `set_reminder`：固件提醒间隔；0 关闭固件提醒。桌面端仍按自身设置计算。
- `set_scale`：每克 ADC 计数，需用已知重量校准，不能直接照搬示例值。
- `set_cup_calibration`：空杯和满杯总重；仅空杯模式传 `full_g=0`，换杯需重做。
- `calibrate_empty`：确认杯垫无物品后归零，会清除旧杯子标定。
- `get_config`：返回设备配置，本机尚无空杯标定时可导入设备标定。

旧命令 `estimate_on_refill` 返回 `ok:0`。未知或无效命令以实现校验为准。协议没有序列号、请求关联 ID 或重试幂等键，应避免重复事件被当作新的饮水。

## 变更约定

同步修改固件定义与实现、协议测试、桌面端解析和本文。不要把 `weight_g` 改成净水量，或把上电累计改成每日累计却保留原字段名。
