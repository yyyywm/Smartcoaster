# 第三方组件与参考资源

项目 MIT 仅覆盖原创内容，不替代第三方许可。分发包需保留实际依赖的许可；版本以 `build-dependencies.txt` 为准。

| 组件 | 用途 | 上游许可入口 |
|---|---|---|
| CPython | Python 运行环境 | [CPython LICENSE](https://github.com/python/cpython/blob/3.11/LICENSE) |
| Tcl/Tk | Tkinter 运行库 | [Tcl/Tk license](https://www.tcl-lang.org/software/tcltk/license.html) |
| Pillow | 图像与界面绘制 | [Pillow LICENSE](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| pyserial | 串口 | [pyserial LICENSE](https://github.com/pyserial/pyserial/blob/v3.5/LICENSE.txt) |
| pystray | 系统托盘 | [COPYING](https://github.com/moses-palmer/pystray/blob/v0.19.5/COPYING)、[COPYING.LGPL](https://github.com/moses-palmer/pystray/blob/v0.19.5/COPYING.LGPL) |
| six | pystray 依赖 | [six LICENSE](https://github.com/benjaminp/six/blob/main/LICENSE) |
| PyInstaller | 构建工具与启动器 | [COPYING.txt](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt) |
| ESP-IDF | SDK，不含在仓库 | [ESP-IDF LICENSE](https://github.com/espressif/esp-idf/blob/v5.3/LICENSE) |

本项目未修改这些库源码。部分 wheel 没有附完整许可，发布前应按版本补齐。打包脚本仅能收集环境中存在的文件，不代表自动完成全部分发合规检查。

`LICENSES/pyserial-3.5.txt` 保存 pyserial v3.5 上游的完整许可，打包时补入 `licenses/`。CPython、Pillow、pystray、six 和已安装 Tk 的许可从当前构建环境收集；用户修改或升级依赖后须重新核对。

## USB-C STEP 参考

本地曾用 `USB_C_Receptacle_HRO_TYPE-C-31-M-12.step` 检查接口外形。旧记录标注来自 Nabu Casa，STEP 头包含 LightBlue / FreeCAD / KiCad StepUp 信息，但当前未追溯到精确上游版本和独立许可。

该文件仅保留为 `cad/references/` 下的可选本地参考，被 Git 忽略，不纳入公开仓库或 Windows 分发包。生成脚本不依赖它。不能用 Nabu Casa 某个仓库的总体许可代替该文件的来源核实。
