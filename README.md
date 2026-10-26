# ResearchFlow AI Windows Beta 0.3.0

## 安装与开始

1. Windows 10 22H2 或 Windows 11 x64：双击 ResearchFlowAI-Setup.exe 安装，无需预装 Python、Conda、CUDA 或 Ollama。当前安装向导为英文，助手为中文。
2. 在“首次配置与诊断”选择本地或云端，点击“保存并配置 / 重试”。本地优先复用已有 Ollama 和模型；没有时联网下载并验证官方安装器签名，再下载模型并执行真实推理检查。
3. 在其他应用中用鼠标选中文字，按窗口顶部显示的快捷键唤起助手，然后选择翻译、润色、纠错或解释。默认 **Ctrl+Alt+G**；如被原工具占用，自动尝试 **Ctrl+Alt+R**，再尝试 **Ctrl+Shift+Space**。
4. 翻译自动判断中英方向；润色保留原文语言；纠错只返回修正后的正文；解释用中文。结果生成完整后可“一键复制”。翻译、润色、纠错还可“一键替换原选区”。

## 一键替换

快捷键唤起时记录原窗口及原选区。替换前重新激活原窗口、重新读取选区并核对原文；窗口关闭、选区变化、输入被修改、只载入过长选区的一部分或输出未完整完成时不执行替换。

原应用必须可编辑，并且选区需保持不变。替换通过系统粘贴发给原应用；无法保证目标应用接受粘贴。请核对，必要时在原应用 Ctrl+Z 撤销。解释结果可复制，不提供替换。手动粘贴的原文没有原窗口关联，只能一键复制。

如快捷键冲突、权限不同、扫描 PDF、密码框或应用不支持复制，可改用手动复制粘贴。采集会尝试恢复旧的纯文本剪贴板，不能完整保留富文本、图片、多格式或剪贴板历史；替换后剪贴板保留生成结果。

## API 供应商与自定义模型

预设 DeepSeek 官方、阿里云百炼北京/新加坡、硅基流动、月之暗面 Kimi。另有自定义选项，可填任意兼容 Chat Completions 的 HTTPS API 基础地址。

选择供应商会填入示例地址和模型 ID，地址和模型名均可继续修改。模型名是服务商实际支持的 ID，不是任意昵称；服务商可能调整可用模型，按账户控制台为准。API Key 必须由对应供应商创建，不是登录密码，也不会根据密钥自动识别供应商。阿里云密钥和地址还需地域对应，业务空间专属域名可直接修改地址填写。

切换供应商或修改 API 地址会清空旧密钥并取消发送确认，防止把上一家的密钥误发给另一家。地址可填基础 URL；若粘贴了以 /chat/completions 结尾的完整地址会自动去除该尾段。拒绝 HTTP、带凭证 URL 以及 HTTP 重定向。

Key 只在本次进程内存中保存；不写设置或诊断日志，退出需重新输入。云端模式需主动勾选文本发送确认，可能产生服务商 API 费用。本地模式不需要密钥，也不会在失败时自动切到云端。

预设的示例名称按本次查询官方文档填写；预设不等于已使用真实账户完成兼容性验证。云端请求本次没有真实账户测试。

## 本地模型与空间

下列数值为 Ollama 标签对应权重的近似磁盘占用，不是内存需求或下载成功保证；实际以引擎进度为准。

| 模型 | 权重约占用 | 推荐总内存 | 模型盘至少空闲 |
|---|---:|---:|---:|
| deepseek-r1:1.5b | 1.1 GB | 8 GiB | 4 GiB |
| deepseek-r1:7b | 4.7 GB | 16 GiB | 9 GiB |
| deepseek-r1:8b | 5.2 GB | 16 GiB | 10 GiB |
| deepseek-r1:14b | 9.0 GB | 32 GiB | 18 GiB |
| qwen2.5:0.5b | 398 MB | 4 GiB | 2 GiB |
| qwen2.5:1.5b | 986 MB | 6 GiB | 4 GiB |
| qwen2.5:3b | 1.9 GB | 8 GiB | 5 GiB |
| qwen2.5:7b | 4.7 GB | 16 GiB | 9 GiB |
| llama3.2:1b | 1.3 GB | 6 GiB | 4 GiB |
| llama3.2:3b | 2.0 GB | 8 GiB | 5 GiB |

门槛允许约 10% 硬件预留内存误差；运行其他程序时仍可能内存不足。Ollama 安装另需系统盘至少 6 GiB、临时目录至少 3 GiB 空闲。权重尺寸由官方标签给出，R1 各大小为蒸馏/对应版本，完整模型权重不包含在本安装包内。

检测内存、当前可用内存、GPU 名称和磁盘；GPU 加速最终由 Ollama 判断，CPU-only 可能较慢。模型路径优先读取 OLLAMA_MODELS，默认 %USERPROFILE%\.ollama\models；外部启动服务若使用不同环境变量，需自行核对实际目录。

下载会显示已完成/总量，模型进度以当前层为单位，失败自动重试最多三次，也可手动重试。分块续传由 Ollama 管理。取消需等待当前读取返回（最长约 180 秒）；官方安装器运行期间需等它结束，不强行中断安装；关闭客户端流不保证共享服务立即停止下载。

## 使用偏好与托盘

“使用偏好”页有两个独立开关，默认关闭，勾选后立即保存：

- **登录 Windows 后自动启动（后台运行）**：使用当前用户的启动项，不要求管理员权限。后台启动需已保存配置；首次使用仍显示配置页。
- **划词弹窗点击其他应用时自动隐藏**：只对快捷键唤起的划词弹窗生效；托盘打开的常规配置窗口不会因失焦自动隐藏。

系统托盘菜单可打开、隐藏、退出。隐藏不结束当前任务；窗口顶部显示的快捷键或再次双击程序入口也可唤回。同一登录会话只运行一份。关闭窗口或托盘“退出”结束程序；有任务时请先取消并等任务结束。

若托盘和快捷键均未就绪，程序会拒绝隐藏，避免无法重新打开。卸载会删除指向本安装路径的 ResearchFlow AI 开机启动项。

## 日志、卸载与边界

设置和轮转诊断日志：%LOCALAPPDATA%\ResearchFlowAI。日志仅记录时间与白名单事件代码，不包含原文、生成结果、密钥或服务器响应，无遥测。Ollama 自身日志由它独立管理，不在本助手的日志隐私保证范围内。

Windows“已安装的应用”可卸载助手。不会删除共享 Ollama 或模型，也不清除用户配置文件；需要完全清理时，退出后自行删除上述 ResearchFlowAI 数据目录。用户原 DeepSeekAssistant 项目不受本次交付旧版清理影响。

输入最多 12,000 字符，模型上下文为 4096 token，建议长文分段。仅对已验证的 Qwen3 架构 R1 8B 复用快速正文输出；1.5B 和其他模板按原生方式推理。模型输出不保证事实、统计解释、术语和引文准确。达到输出长度上限会明确失败，不启用一键替换。

本 Beta 未进行发布者代码签名，可能被 SmartScreen 或安全软件提示。其他电脑、不同权限应用、不同缩放、真实云端和首次全新环境部署仍需试装；不能保证所有设备 100% 成功。

## 开发与验证

Windows x64 + Python 3.13，安装 requirements.txt，使用 Inno Setup 6.7.3。源码目录执行 build.ps1 -InnoCompiler <ISCC.exe绝对路径>，安装包输出上一级；开发环境依赖不需要试装用户自行安装。

- python tests.py：引擎、设置、模型目录和 Windows 集成逻辑检查，外部键盘操作及注册表调用使用模拟。
- python ui_checks.py report.json：无网络、无外部键盘注入的界面组件检查。
- ResearchFlowAI.exe --self-test report.json：冻结运行时、Tk、托盘依赖、硬件和四种提示词自检。

溯源原文位于 provenance/，不参与执行。prompts.py 沿用并调整原项目提示词，纠错改为只输出修正文；core.py 管理部署、推理和日志；catalog.py 管理供应商与模型；windows_integration.py 管理选区/替换及启动项；app.py 管理界面、快捷键、托盘和隐藏。

## 官方参考（2026-10-25 查询）

- [DeepSeek API](https://api-docs.deepseek.com/)
- [阿里云兼容接口与地域](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)
- [SiliconFlow 接口](https://docs.siliconflow.cn/docs/api/chat-completions-post)
- [Kimi API](https://platform.kimi.com/docs/get-api-key)
- [DeepSeek-R1 模型大小](https://ollama.com/library/deepseek-r1/tags)
- [Qwen2.5 模型大小](https://ollama.com/library/qwen2.5/tags)
- [Llama3.2 模型大小](https://ollama.com/library/llama3.2/tags)
- [Ollama Windows](https://docs.ollama.com/windows)

