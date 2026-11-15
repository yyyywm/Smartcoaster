# 旧版 COM 生成脚本

这些脚本保存早期模型的生成过程，仅作备份和特殊情况下的备选。**默认使用 SolidWorks MCP，日常不要直接执行这些脚本。**

| 文件 | 原用途 |
|---|---|
| `generate_sensor_proxy.py` | 生成传感器占位零件和 STEP |
| `generate_coaster.py` | 生成底座 v4、上盘 v5 |
| `assemble_coaster.py` | 生成当前 v5 三组件布局装配 |
| `requirements.txt` | 可选的 pywin32 依赖，不属于桌面端依赖 |

已将路径适配到新目录：原生输出在 `cad/models/`，传感器 STEP 在 `cad/exports/step/`，装配预览在 `cad/exports/previews/`。此次只做语法与路径检查，没有运行重生成，也不保证生成脚本保留后续手工或 MCP 所做的模型修改。

确有特殊情况需要使用时，先备份当前设计，检查 SolidWorks 2023 模板路径、依赖及覆盖目标，并通过 MCP 或用户确认没有其他自动化任务占用 SolidWorks。
