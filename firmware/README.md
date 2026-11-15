# ESP32-C3 固件

当前 `sdkconfig` 的目标为 `esp32c3`，初始化版本为 ESP-IDF 5.3.0。CMake 工程标识沿用 `esp32c3_hx711`，构建二进制保留该名称；产品统一称 SmartCoaster。

## 接线

| HX711 | ESP32-C3 |
|---|---|
| DOUT / DT | GPIO4 |
| SCK / PD_SCK | GPIO5 |
| VCC | 3.3V |
| GND | GND |

原生 USB Serial/JTAG 使用 GPIO18/19，USB 线须支持数据。HX711 GPIO 可在 `menuconfig` 修改，不要占用 USB 引脚。

## 构建与烧录

安装并导出 ESP-IDF 环境后执行，不将 SDK 拷入仓库：

```powershell
# 先执行本机实际 ESP-IDF 安装目录中的 export.ps1
cd firmware
idf.py build
idf.py -p COMx flash
idf.py -p COMx monitor
```

`COMx` 换成真实端口；监视器和桌面端不能同时使用串口。已有 `sdkconfig` 已设 ESP32-C3；仅真正切换目标时运行 `idf.py set-target esp32c3`，它可能重置配置。

`build/`、`cmake-build-debug/` 和日志是可再生文件，不入 Git。`sdkconfig` 保留版本管理。完整构建需要 IDF 工具链，宿主测试不能替代它。

## 称重与标定

- 默认 384.7 counts/g 仅是现有配置，换传感器应以已知重量重新校准。
- 约 10 Hz，10 点稳定窗口、极差阈值 4 g；净减少严格大于 5 g 记饮水，净增加大于 15 g 记补水。
- 无杯时学习零点；变化超过 10 g 时最多每 15 分钟保存一次。
- 空杯标定过滤异常低重量；满杯标定提供容量上界。在线且稳定时，桌面端按总重减空杯重显示水量。
- 净增加不推算期间饮水；需后续可确认净减少才记账。
- NVS 保存配置与稳定参考，上电累计不等于桌面端当天累计。

见 [架构](../docs/ARCHITECTURE.md) 和 [协议](../docs/PROTOCOL.md)。

## 宿主测试

仓库根目录执行 `make -C firmware/tests test`，不依赖 IDF/板卡，详见 [tests/README.md](tests/README.md)。

## 历史 SDK 补丁

旧开发记录曾在本机 SDK 的 `components/esp32c3/clk.c` 对 `esp_rom_uart_tx_wait_idle(CONFIG_ESP_CONSOLE_UART_NUM)` 加上 `#if CONFIG_ESP_CONSOLE_UART` 条件，避免 USB Serial/JTAG 控制台时使用无效 UART 号。补丁位于仓库外，不随 Git 克隆传播，本次没有重新验证当前 SDK 状态。

上游说明：[Espressif AR2025-006](https://documentation.espressif.com/AR2025-006_Usage_Instructions_for_Configuring_the_Console_Output_Channel_for_the_ESP32-C3_Chip_Revision_v1.1.html)。受影响组合按上游说明处理；升级后先比较实际源码，不把旧本机补丁当作所有版本都需要的通用步骤。
