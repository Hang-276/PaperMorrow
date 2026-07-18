# PaperMorrow 桌面应用

桌面版把前端、后端和本地数据库封装在同一个应用中。API Key、数据库、笔记与 Wiki 不会写进安装包：macOS 存放于 `~/Library/Application Support/PaperMorrow`，Windows 存放于 `%APPDATA%\PaperMorrow`。

## macOS

在项目根目录执行：

```bash
.venv-paper/bin/python -m pip install -r requirements-desktop.txt
bash scripts/build_macos_app.sh
```

产物为 `desktop_dist/PaperMorrow.app`。当前是未签名的本地开发版；首次打开若被系统拦截，可在“系统设置 → 隐私与安全性”中选择仍要打开。正式分发需要 Apple Developer ID 签名与公证。

## Windows

在安装了 Python 3.11 与 Node.js 20 的 Windows PowerShell 中执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows_app.ps1
```

产物为 `desktop_dist\PaperMorrow\PaperMorrow.exe`。Windows 10/11 通常已包含 WebView2；较旧环境可安装 Microsoft WebView2 Runtime。正式分发可以再加代码签名与安装器。

## GitHub 自动构建

仓库自带 `Build desktop apps` 工作流。在 GitHub 的 Actions 页面手动运行后，会同时得到 macOS 与 Windows 两个可下载构建产物；推送形如 `v0.3.0` 的 tag 也会触发构建。
