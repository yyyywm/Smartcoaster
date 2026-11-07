# 宿主侧单元测试

不依赖 ESP-IDF、不需要硬件，直接把核心逻辑源码编译到 PC 上运行，用于在开发固件新功能/改协议前先验证逻辑正确性。

## 覆盖范围

| 测试 | 对象 | 覆盖内容 |
|---|---|---|
| `test_coaster.c` | `components/coaster/coaster.c` | 参数校验、空载基线自学习（快下学/温漂）、放杯去抖与 `cup_placed`、拿杯 `cup_removed`、**差值法喝水结算**、阈值内不记账、在位喝水/加水（迁移）、续杯估算开关、`min_cup_g` 自学习、`set_baseline` / `set_scale`、空指针安全 |
| `test_protocol.c` | `components/coaster/protocol.c` | 设备 → PC 的每一条 JSON Lines 文本格式（`event` / `status` / `remind` / `ack` / `config`）**与协议文档逐字节一致** |

`stubs/` 下提供宿主端最小的 `cJSON` / `freertos` / `ESP_LOG` 桩，使 `protocol.c` 能在 PC 上编译运行。

未覆盖（需 IDF / 真机）：`storage.c` 的 NVS 读写、`coaster_main.c` 的整体流程、`hx711.c` 的 SPI 时序。

## 运行

需要 `gcc`（Windows 用 MinGW-w64；Linux/macOS 的 `cc` 亦可）。在本目录执行：

```powershell
make test      # 编译并运行全部测试
make all       # 只编译
make clean     # 清理
```

MinGW 环境下若 `make` 找不到编译器，可显式指定：

```powershell
make test CC=gcc
```

## 编写约定

- 每个宏 `TEST_CASE("描述")` 是一段独立用例，使用 `CHECK / CHECK_INT / CHECK_FLOAT / CHECK_STR` 断言，失败会打印文件、行号、期望/实际值。
- 测试结束 `return test_report();`，有失败时进程返回非 0，可直接接入 CI。
- 建议：改状态机逻辑或协议格式后先 `make test` 通过，再 `idf.py build` 烧录真机。
