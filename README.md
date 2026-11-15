# SmartCoaster · 智能杯垫

An ESP32-C3 + HX711 smart coaster with a Windows hydration reminder app and SolidWorks enclosure designs.

通过称重变化记录饮水，配合桌面端进行定时提醒和每日目标统计。仓库包含 ESP32-C3 固件、Python/Tkinter 桌面端、SolidWorks 外壳设计和宿主测试。

- **桌面端**：工作时段提醒、全屏背景、多显示器、系统托盘、自动串口连接和双点杯子标定。
- **月历统计**：周一开始、整月显示，达标绿色、未达标红色；无记录及未来日期灰色。
- **本地记录**：SQLite 保存设置和饮水记录，可导出 CSV，没有云同步服务。
- **固件**：只按可确认的净重量减少计量；补水不反推期间饮水量，配置和运行状态保存到 NVS。
- **外壳**：可编辑零件、装配、生成脚本和 STL。当前仍是布局原型，需实物试装。

称重减少不能证明水被喝下，倒水、换杯和传感器误差都可能影响结果。本项目不是医疗计量设备。

## 快速开始

### Windows 用户

取得分发 ZIP 后解压，运行 `SmartCoaster.exe`，无需安装 Python。连接已烧录配套固件的杯垫，首次在“设置”中配置时间、目标及杯子标定。

顶部导航：**总览 → 统计 → 设置 → 数据**。设备选择、刷新和连接按钮位于顶部右侧、COM 状态左边。详细说明见 [桌面版使用说明](desktop/DISTRIBUTION.md)。

本地构建 ZIP 位于 `desktop/release/`，不提交到 Git。仓库不包含已发布的安装包或固件二进制；公开发布时可把验证后的 ZIP 附到 GitHub Release。

### 开发者

本机复用已有 Conda 环境 `dsh_coaster`，不创建项目 `.venv`。从仓库根目录执行：

```powershell
conda run --no-capture-output -n dsh_coaster python -s -X utf8 -m pip install -r desktop/requirements.txt
conda run --no-capture-output -n dsh_coaster python -s -X utf8 desktop/smart_coaster.py --selftest
conda run --no-capture-output -n dsh_coaster python -s -X utf8 desktop/smart_coaster.py --simulate --db demo.db
```

新贡献者如果尚无该环境，可先自行执行 `conda create -n dsh_coaster python=3.11 pip`。日常开发和打包复用已有环境。演示数据库与正式数据库分开，`demo.db` 不纳入 Git。

Windows 打包：

```powershell
powershell -NoProfile -File desktop/build.ps1
```

固件构建和接线见 [firmware/README.md](firmware/README.md)，CAD 使用见 [cad/README.md](cad/README.md)。

## 目录

```text
Smartcoaster/
├── desktop/            桌面端源码、资源、测试和 Windows 打包入口
│   ├── coaster_app/    规则、存储、串口、月历和界面
│   ├── assets/         图标及生成脚本
│   └── tests/          离线规则与 GUI 测试
├── firmware/           ESP-IDF 工程
│   ├── components/     HX711 驱动、称重状态机、NVS、协议
│   ├── main/           采样、命令处理与状态上报
│   └── tests/          GCC 宿主测试，不依赖硬件
├── cad/                SolidWorks 零件、装配和生成脚本
│   ├── models/         当前原生设计与 v5 装配
│   ├── archive/        历史版本及独立装配引用
│   ├── scripts/legacy/ 旧 COM 脚本；日常操作使用 MCP
│   ├── exports/stl/    当前外壳 STL 导出
│   ├── exports/step/   中性格式导出
│   └── references/     外部参考说明；未核实许可的模型仅保留本地
├── docs/               架构、协议、维护发布与验证记录
├── CONTRIBUTING.md     贡献与验证约定
├── THIRD_PARTY_NOTICES.md
└── LICENSE             MIT
```

`desktop/` 由原 `host/` 更名，Python 包名 `coaster_app` 保持不变；CAD 原生文件名保留，以免破坏装配引用。GitHub 仓库为 [yyyywm/Smartcoaster](https://github.com/yyyywm/Smartcoaster)，本地旧文件夹名 `esp32c3_hx711` 和固件 CMake 工程标识不影响克隆和运行。

## 文档索引

| 文档 | 内容 |
|---|---|
| [桌面端](desktop/README.md) | 环境、运行、界面功能和提醒规则 |
| [用户分发说明](desktop/DISTRIBUTION.md) | 免安装启动、标定、退出和备份 |
| [固件](firmware/README.md) | 接线、构建烧录、校准和 SDK 注意事项 |
| [CAD](cad/README.md) | 当前版本、装配顺序、尺寸和验证限制 |
| [架构](docs/ARCHITECTURE.md) | 模块边界、数据流和持久化 |
| [串口协议](docs/PROTOCOL.md) | JSON Lines 事件、命令与边界 |
| [维护与发布](docs/MAINTENANCE.md) | 依赖、打包、清理、升级和 Git 发布 |
| [测试](docs/TESTING.md) | 验证命令、覆盖范围及验证记录 |
| [贡献](CONTRIBUTING.md) | 命名、变更范围与提交检查 |
| [变更记录](CHANGELOG.md) | 当前未发布功能及目录迁移 |

## 许可证

项目自行编写的代码、文档和自行创建的 CAD 设计采用 [MIT](LICENSE)。第三方运行库、SDK 和参考资源仍遵守各自许可证，见 [第三方说明](THIRD_PARTY_NOTICES.md)。本次整理不重新分发许可未核实的 USB-C STEP 参考模型。
