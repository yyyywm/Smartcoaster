# 开发、维护与发布

## 环境

本机复用 Conda 环境 `dsh_coaster`，不创建 `.venv`，不往 base 或用户级 site-packages 安装依赖。`python -s` 忽略用户级包，`-X utf8` 避免 Windows 默认编码影响中文文件。

```powershell
conda env list
conda run --no-capture-output -n dsh_coaster python -s -X utf8 -m pip install -r desktop/requirements.txt
conda run --no-capture-output -n dsh_coaster python -s -X utf8 desktop/smart_coaster.py --selftest
```

`requirements.txt` 定义运行依赖范围；`requirements-build.txt` 固定打包器并引用运行依赖。每个分发包的 `build-dependencies.txt` 记录真实版本，不提交本地环境目录。

## Windows 打包

从仓库根目录运行：

```powershell
powershell -NoProfile -File desktop/build.ps1
# 依赖已满足时：
powershell -NoProfile -File desktop/build.ps1 -SkipInstall
```

脚本只使用已有环境。`-CondaEnvironment 名称` 可指定其他已有 Conda 环境；不存在时修复环境，不自动改用 base。流程：安装依赖 → 桌面端全测 → PyInstaller GUI EXE → 整理说明、许可和校验 → ZIP。

- `desktop/build/`：分析缓存和中间 EXE，可再生。
- `desktop/release/SmartCoaster-Windows-x64-日期时间/`：可运行分发目录。
- 同名 `.zip`：用于分发。包内 `SHA256.txt` 校验 EXE，不是 ZIP。
- `desktop/dist/` 是旧布局，后续不再使用；每次构建使用独立目录，避免覆盖运行中的旧版。

单文件运行时会将内置资源释放到临时目录。不要把数据库或用户图片放入 PyInstaller `datas`；数据库继续位于用户数据目录。

## 发布前

1. 运行 [测试清单](TESTING.md)，确认导航、COM 控件、月历、托盘和提醒背景。
2. 演示使用独立 `--db`；无硬件时不要声明真实称重已验证。
3. 解压 ZIP 检查启动和 SHA256，确认没有数据库、个人图片、绝对开发路径或令牌。
4. 检查 `LICENSE` 与 `THIRD_PARTY_NOTICES.md`，保留依赖许可。当前没有自动代码签名步骤。
5. 提交并推送到 `https://github.com/yyyywm/Smartcoaster.git`。二进制需另附 GitHub Release；`git push` 不上传被忽略的分发包。

保留已有 Git 历史，目录更名 `host/` → `desktop/` 在新提交记录，不重写过去提交。

## 清理与归档

可再生内容：`__pycache__`、`.pyc`、日志、`desktop/build/`、旧分发版、`firmware/build/`、`firmware/cmake-build-debug/`。清理前退出占用进程，逐个确认绝对路径。不使用未经检查的 `git clean -fdx`，它会清掉被忽略的个人文件。

本地保留最新已验证 ZIP 及分发目录，旧版本移出仓库归档。SolidWorks `~$*` 是临时锁文件，确认文档关闭后处理；历史 `v1`–`v5` 原生设计不是缓存，版本组合见 `cad/README.md`。

## 升级、备份和回退

- 先退出再换 EXE。数据库不在程序目录，换程序不会自动删除记录。
- 完整备份：退出后复制整个 `%LOCALAPPDATA%\SmartCoaster`，包括数据库与 `reminder_images/`。CSV 不含设置和图片，也没有导入恢复功能。
- 当前 SQLite 通过 `CREATE TABLE IF NOT EXISTS` 初始化；本次月历未改表结构。以后改表须显式设计迁移和备份。
- 回退 EXE 前确认数据库兼容，不把个人数据库提交到 Git。

## 命名

目录小写，桌面端称 `desktop`，嵌入式称 `firmware`；Python 保持 `snake_case`，已有包名 `coaster_app` 不变，产品统一称 SmartCoaster。原生 CAD 文件名和固件工程标识保留，避免纯命名整理破坏引用和构建。
