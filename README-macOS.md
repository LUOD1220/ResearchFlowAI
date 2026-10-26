# ResearchFlow AI 0.3.0 — Apple Silicon 开发与构建包

此包包含真实的 macOS 适配源码和 arm64 构建脚本。**当前交付没有预先构建的 Mac .app 或 .dmg，也没有 Mac 实机验收结果。** Windows 机器不能用 PyInstaller 直接生成可验收的 macOS 应用。请在你的 M 系列 Mac 上执行下面的构建，或在那台 Mac 的 Codex 中打开本工程继续构建和测试。

## 在 M 系列 Mac 上构建

1. 使用 macOS 14 或更新版本，在本机解压构建包。使用原生 Apple Silicon 环境，避免 Rosetta。
2. 构建电脑需要带 tkinter 的 arm64 Python 3.11 或更新版本，推荐 Python 3.13（可从 [Python 官方 macOS 下载页](https://www.python.org/downloads/macos/)安装）。这只是构建要求，生成的 .app 已包含 Python 运行时，普通试装电脑无需预装 Python。
3. 双击 `build_macos.command`。如果文件管理器没有执行它，可在该目录用终端执行 `bash build_macos.command`。脚本创建独立虚拟环境、安装依赖、运行可移植逻辑检查，再构建 arm64 应用和磁盘镜像。
4. 构建成功后，`release-macos/` 包含 `ResearchFlowAI-macOS-arm64.dmg`、`.app.zip`、运行时自检 JSON 及依赖清单。若中途失败，请保留完整输出供排查。
5. 打开本机生成的 DMG，把 ResearchFlowAI.app 拖到 Applications 后运行。先完成下面的权限配置，再验证划词和替换。

该脚本使用本机 ad-hoc 签名以满足 Apple Silicon 的可执行要求，**不等于 Developer ID 签名或 Apple 公证**，不能承诺在其他 Mac 上无提示启动。正式对外分发仍需要开发者签名、公证与跨设备验收。程序不删除隔离属性，不关闭 Gatekeeper，不自动批准系统权限。

## Mac 功能及权限

- 快捷键为 **Control + Option + G（⌃⌥G）**；避免占用浏览器常见的 Command+Option+G。通过全局快捷键唤起后，选择翻译、润色、纠错、解释。
- 菜单栏的 **RF** 提供打开、隐藏、退出。普通窗口关闭退出；后台启动/失焦隐藏遵循使用偏好。
- 划词通过原应用的 Command+C 获取文本；替换前重新激活原应用并核对选区，再用 Command+V 粘贴。仅支持允许复制/粘贴的文本；只读、密码框、扫描图片等可能不适用。剪贴板只尝试恢复纯文本，不能保证完整保留富文本、图片或历史。
- 在 macOS“系统设置 → 隐私与安全性”中手动为 ResearchFlowAI.app 允许 **辅助功能** 和 **输入监控**，然后重启应用。未授权时可先手动粘贴。开发时若直接运行 Python，权限可能归属于 Python/终端；应以打包后安装的 .app 验收。权限必须由你操作，程序不会自动授予。
- “使用偏好”提供四套主题和 70%–100% 不透明度。设置保存于 `~/Library/Application Support/ResearchFlowAI/settings.json`；密钥不保存。
- 自启动使用当前用户的 `~/Library/LaunchAgents/com.researchflowai.desktop.plist`，开关控制它是否存在。请在应用已放到最终位置后启用，避免移动 .app 后启动路径失效。
- 同一用户只运行一份，通过文件锁和唤回标记恢复已有窗口，没有开放本地网络控制端口。

## 模型与 Ollama

优先复用现有 Ollama 和模型，**切换模型不删除旧权重**。模型目录默认 `~/.ollama/models`，可读取 OLLAMA_MODELS。

没有引擎时，配置流程会下载官方 Ollama.dmg，尝试验证代码签名、Gatekeeper 安全评估和应用标识，再复制到当前用户的 `~/Applications` 并启动。该路径尚未在 Mac 实测；若验证或安装失败，会停止并提示手动从 [Ollama 官方下载页](https://ollama.com/download/mac)安装后重试。程序不会覆盖已有但无法识别的 Ollama.app，也不会绕过安全检查。

模型下载显示进度并支持有限重试，完成后执行真实推理检查。Apple Silicon 使用统一内存；可用内存与实际速度取决于同时运行的其他软件。云端模式沿用供应商、自定义地址和密钥仅存内存的设置。

## 必须在你的 Mac 上完成的验收

- 实际构建、.app 启动、菜单栏、四种主题、透明度及重启后设置保存。
- 辅助功能与输入监控未授权/授权后行为；快捷键是否与 VoiceOver 或其他应用冲突。
- TextEdit、Safari、Word 等具体应用中的选择、采集、复制、替换和撤销；输入改变或原应用关闭时必须拒绝替换。
- 已有 Ollama 的复用、全新安装、真实模型下载、断网重试和推理。
- 登录后的自启动、隐藏后唤回，以及同一用户单实例。

Windows 上的模拟检查和源码语法检查不能代替以上验收。Mac 端未验证的功能不得表述为已经成功运行。

卸载时退出应用、关闭本助手的登录启动开关，再把本助手 .app 移到废纸篓。保留或自行清理本助手的 Application Support 数据；**不要删除 Ollama 或 `.ollama` 来卸载本助手**。

官方参考：[PyInstaller 使用说明](https://pyinstaller.org/en/stable/usage.html)、[pynput macOS 权限限制](https://pynput.readthedocs.io/en/latest/limitations.html)、[Ollama macOS 要求](https://docs.ollama.com/macos)。
