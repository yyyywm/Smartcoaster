# 贡献指南

先读 [README](README.md)、[架构](docs/ARCHITECTURE.md) 和对应子目录说明。反馈问题时提供环境版本、复现步骤、期望与实际结果；日志及数据库须先去除个人信息。

## 开发约定

- 本地复用 `dsh_coaster` Conda 环境，新贡献者可自行建立同名环境，不提交环境目录。
- 上位机在 `desktop/`，ESP-IDF 在 `firmware/`，机械设计在 `cad/`，通用文档在 `docs/`。
- Python 用 `snake_case`，不无目的地改公共包名和 CAD 文件名。
- 规则改动覆盖实际行为；小界面改动复用布局检查，不堆叠复述实现的测试。
- 改协议时同步固件、宿主测试、桌面解析和协议文档。
- 新 CAD 版本在 `cad/README.md` 写明零件组合及未验证项，保留旧装配引用。

## 提交前

```powershell
conda run --no-capture-output -n dsh_coaster python -s -X utf8 desktop/smart_coaster.py --selftest
make -C firmware/tests test
git diff --check
git status --short
```

按范围运行必要检查，提交/PR 说明结果及限制；提交消息说明目的，可用 `feat:`、`fix:`、`docs:`、`chore:` 等前缀。

不提交数据库、提醒照片、环境、IDE 配置、SolidWorks 锁文件、SDK、构建缓存、EXE 和 ZIP。分发包放 GitHub Release，保留许可证与第三方声明。

原创贡献采用项目 MIT。第三方资源必须有可核实来源及原许可，不能因为公开可下载就改标 MIT。
