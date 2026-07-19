# PaperMorrow 桌面应用

桌面版把前端、后端和本地数据库封装在同一个应用中。API Key、数据库、笔记与 Wiki 不会写进安装包：macOS 存放于 `~/Library/Application Support/PaperMorrow`，Windows 存放于 `%APPDATA%\PaperMorrow`。

## macOS

在项目根目录执行：

```bash
.venv-paper/bin/python -m pip install -r requirements-desktop.txt
bash scripts/build_macos_app.sh
```

产物为 `desktop_dist/PaperMorrow-macOS.dmg`。普通用户打开 DMG 后，把 PaperMorrow 拖入“应用程序”即可。当前构建使用本机临时签名；首次打开若被系统拦截，可右键应用选择“打开”，或在“系统设置 → 隐私与安全性”中允许。完全消除安全提示仍需要 Apple Developer ID 签名与公证。

## Windows

在安装了 Python 3.11 与 Node.js 20 的 Windows PowerShell 中执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows_app.ps1
```

产物包括 `desktop_dist\PaperMorrow-Windows-Setup.exe` 安装器和 `PaperMorrow-Windows-Portable.zip` 便携包。普通用户只需双击安装器，随后从开始菜单或桌面图标启动，无需安装 Python 或 Node.js。数据库、API Key、论文、笔记和演示文稿保存在 `%APPDATA%\PaperMorrow`，升级或卸载应用都不会删除这些内容。Windows 10/11 通常已包含 WebView2；较旧环境需安装 Microsoft WebView2 Runtime。未使用商业代码签名证书时，Windows 可能显示 SmartScreen 提示。

## GitHub 自动构建

仓库自带 `Build desktop apps` 工作流。在 GitHub 的 Actions 页面手动运行后，会同时得到 macOS 与 Windows 两个可下载构建产物；推送形如 `v0.4.0` 的 tag 也会触发构建。
