"""macOS hardware and official Ollama deployment; import-safe on Windows."""
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import urllib.request


def command(args, timeout=20):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True).stdout.strip()


def mac_hardware():
    import core
    total = int(command(['/usr/sbin/sysctl', '-n', 'hw.memsize'])) / 2**30
    available = 0.0
    try:
        stats = command(['/usr/bin/vm_stat'])
        page_size = int(re.search(r'page size of (\d+)', stats).group(1))
        pages = sum(int(m.group(1)) for label in ('Pages free', 'Pages inactive', 'Pages speculative')
                    if (m := re.search(re.escape(label) + r':\s+(\d+)', stats)))
        available = pages * page_size / 2**30
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        pass
    gpu = 'Apple Silicon 统一内存 / Metal' if platform.machine() == 'arm64' else 'Intel Mac / CPU'
    model_dir = Path(os.environ.get('OLLAMA_MODELS', str(Path.home() / '.ollama' / 'models')))
    return {'ram_gb': round(total, 1), 'available_gb': round(available, 1),
            'model_free_gb': round(core.disk_free(model_dir), 1),
            'system_free_gb': round(core.disk_free(core.DATA), 1),
            'temp_free_gb': round(core.disk_free(tempfile.gettempdir()), 1),
            'model_dir': str(model_dir), 'gpu': gpu, 'arch': platform.machine(),
            'macos_version': platform.mac_ver()[0], 'windows_build': 0}


def mac_ollama_exe():
    found = shutil.which('ollama')
    if found:
        return found
    for p in (Path('/Applications/Ollama.app/Contents/Resources/ollama'),
              Path.home() / 'Applications/Ollama.app/Contents/Resources/ollama',
              Path('/opt/homebrew/bin/ollama'), Path('/usr/local/bin/ollama')):
        if p.is_file():
            return str(p)


def ensure_mac_engine(progress, cancel):
    import core
    exe = mac_ollama_exe()
    if not exe:
        core.DATA.mkdir(parents=True, exist_ok=True)
        dest = core.DATA / 'Ollama.dmg'
        for attempt in range(3):
            core.check_cancel(cancel)
            try:
                progress('下载 Ollama 官方 Mac 安装包…', 0)
                with urllib.request.urlopen('https://ollama.com/download/Ollama.dmg', timeout=60) as r, dest.open('wb') as f:
                    total = int(r.headers.get('Content-Length', 0))
                    count = 0
                    while True:
                        core.check_cancel(cancel)
                        block = r.read(1024 * 1024)
                        if not block:
                            break
                        f.write(block); count += len(block)
                        progress(f'Ollama 下载 {count/2**20:.1f} MB' + (f' / {total/2**20:.1f} MB' if total else ''),
                                 count * 100 / total if total else 0)
                break
            except core.FlowError:
                raise
            except (OSError, ValueError):
                if attempt == 2:
                    raise core.FlowError('NETWORK', 'Ollama Mac 下载失败。请检查网络后重试，或从官网安装。') from None
                cancel.wait(2 ** attempt)
        mount = Path(tempfile.mkdtemp(prefix='ollama-mount-', dir=core.DATA))
        mounted = False
        try:
            command(['/usr/bin/hdiutil', 'attach', str(dest), '-nobrowse', '-readonly', '-mountpoint', str(mount)], 120)
            mounted = True
            app = mount / 'Ollama.app'
            if not app.is_dir():
                raise core.FlowError('INSTALL', '官方镜像中未找到 Ollama.app，请手动安装后重试。')
            progress('验证 Ollama 的签名与 macOS 安全评估…', 0)
            command(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)], 60)
            # Gatekeeper must approve; never remove quarantine or disable it.
            command(['/usr/sbin/spctl', '--assess', '--type', 'execute', str(app)], 60)
            identifier = command(['/usr/libexec/PlistBuddy', '-c', 'Print :CFBundleIdentifier',
                                  str(app / 'Contents/Info.plist')])
            if 'ollama' not in identifier.lower():
                raise core.FlowError('SIGNATURE', 'Ollama 应用标识不符，未安装。')
            core.check_cancel(cancel)
            target = Path.home() / 'Applications' / 'Ollama.app'
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise core.FlowError('INSTALL', '已有 Ollama.app 但无法找到命令行，请完成官方安装后重试；未覆盖现有应用。')
            command(['/usr/bin/ditto', str(app), str(target)], 180)
            progress('请完成可能出现的 macOS 打开确认，然后等待本地服务启动…', 0)
            subprocess.Popen(['/usr/bin/open', str(target)])
        except core.FlowError:
            raise
        except (OSError, subprocess.SubprocessError):
            raise core.FlowError('SIGNATURE', 'Ollama 安装或安全校验未通过；请从官网手动安装后重试。') from None
        finally:
            if mounted:
                try:
                    command(['/usr/bin/hdiutil', 'detach', str(mount)], 30)
                except (OSError, subprocess.SubprocessError):
                    pass
            try:
                mount.rmdir()
            except OSError:
                pass
        exe = mac_ollama_exe()
    if not exe:
        raise core.FlowError('INSTALL', '未找到 Ollama。请完成安装后重试。')
    try:
        core.tags()
        return
    except Exception:
        pass
    subprocess.Popen([exe, 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(90):
        core.check_cancel(cancel)
        try:
            core.tags(); core.event('ENGINE_READY'); return
        except Exception:
            cancel.wait(1)
    raise core.FlowError('NETWORK', 'Ollama 服务尚未就绪，请完成 macOS 打开确认后重试。')
