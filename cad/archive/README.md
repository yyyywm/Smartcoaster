# 历史设计

保留旧原生文件及装配关系，默认不编辑。当前设计在 `../models/`。

| 装配 | 底座 | 上盘 |
|---|---|---|
| `Smart_Coaster_layout_v1.SLDASM` | `Coaster_Base_v1.SLDPRT` | `Coaster_Top_v1.SLDPRT` |
| `Smart_Coaster_layout_v2.SLDASM` | `Coaster_Base_v1.SLDPRT` | `Coaster_Top_v1.SLDPRT` |
| `Smart_Coaster_layout_v3.SLDASM` | `Coaster_Base_v1.SLDPRT` | `Coaster_Top_v3.SLDPRT` |
| `Smart_Coaster_layout_v4.SLDASM` | `Coaster_Base_v3.SLDPRT` | `Coaster_Top_v4.SLDPRT` |

四个装配都使用本目录的 `LoadCell_5kg_75x12p7x7_proxy.SLDPRT`。该副本与整理时当前版本一致，单独保留是为了历史装配不依赖当前目录；后续不自动覆盖。

`Coaster_Base_v2.SLDPRT` 和 `Coaster_Top_v2.SLDPRT` 是中间设计，当前归档装配未引用它们，也予以保留。不要按装配版本号推测它引用的零件版本。

2026-11-15 已通过 MCP 更新引用并打开四个装配，各三个组件均完整加载；复制到另一个目录后再次验证组件均来自新位置。未重新进行尺寸、干涉或实物验证。
