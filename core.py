"""ResearchFlow AI Beta: local engine, provisioning and privacy-safe diagnostics."""
import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import sys
import threading
import re
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from functools import lru_cache

from catalog import MODEL_CATALOG, provider_for_url, normalize_base_url

VERSION = '0.3.2-beta'
IS_MAC = sys.platform == 'darwin'
OS_NAME = 'macOS' if IS_MAC else 'Windows'
LOCAL_URL = 'http://127.0.0.1:11434'
MODELS = {name: spec[:2] for name, spec in MODEL_CATALOG.items()}
DATA = (Path.home() / 'Library' / 'Application Support' / 'ResearchFlowAI' if IS_MAC
        else Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ResearchFlowAI')
_log_lock = threading.Lock()
_settings_lock = threading.Lock()


class FlowError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def init_log():
    DATA.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger('researchflow')
    log.setLevel(logging.INFO)
    if not log.handlers:
        h = RotatingFileHandler(DATA / 'diagnostics.log', maxBytes=256000,
                                backupCount=2, encoding='utf-8')
        h.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        log.addHandler(h)
    return log


def event(code):
    # Only fixed event codes; never log exceptions, HTTP bodies, keys or user text.
    allowed = {'START', 'CONFIG_SAVED', 'ENGINE_READY', 'PULL_RETRY', 'PULL_OK',
               'INFERENCE_OK', 'NETWORK', 'HTTP', 'EMPTY', 'CANCELLED', 'DISK',
               'HARDWARE', 'INSTALL', 'SIGNATURE', 'INTERNAL', 'HOTKEY_CONFLICT',
               'LIMIT', 'REPLACE', 'STARTUP', 'TRAY', 'SELECTION_CHANGED'}
    allowed.update(('TRAY_READY', 'HOTKEY_READY'))
    try:
        allowed.update(('EDIT_RETRY', 'EDIT_REFUSAL', 'APPEARANCE', 'PERMISSION'))
        with _log_lock:
            init_log().info(code if code in allowed else 'INTERNAL')
    except OSError:
        pass  # A full/unwritable log directory must not crash the assistant.


def load_config():
    default = {'mode': 'local', 'model': 'deepseek-r1:1.5b',
               'cloud_url': 'https://api.deepseek.com', 'cloud_model': 'deepseek-flash',
               'provider': 'DeepSeek 官方', 'autostart': False, 'auto_hide': False, 'configured': False,
               'theme': '浅色 · 海蓝', 'opacity': 1.0}
    try:
        obj = json.loads((DATA / 'settings.json').read_text(encoding='utf-8'))
        for k in default:
            if isinstance(obj.get(k), type(default[k])):
                default[k] = obj[k]
        from appearance import valid_opacity, THEMES, DEFAULT_THEME
        default['opacity'] = valid_opacity(obj.get('opacity', 1.0))
        if default['theme'] not in THEMES:
            default['theme'] = DEFAULT_THEME
        default['provider'] = provider_for_url(default['cloud_url'])
        # Old beta saved settings only after successful configuration.
        if 'configured' not in obj:
            default['configured'] = True
        if default['provider'] == 'DeepSeek 官方' and default['cloud_model'] == 'deepseek-chat':
            default['cloud_model'] = 'deepseek-flash'
    except (OSError, ValueError):
        pass
    return default


def save_config(config):
    DATA.mkdir(parents=True, exist_ok=True)
    # API key intentionally excluded; it exists only in process memory.
    keep = {k: config[k] for k in load_config() if k in config}
    with _settings_lock:
        tmp = DATA / 'settings.tmp'
        tmp.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(DATA / 'settings.json')
    event('CONFIG_SAVED')


def disk_free(path):
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    return shutil.disk_usage(p).free / 2**30


def hardware():
    if IS_MAC:
        from macos_support import mac_hardware
        return mac_hardware()
    class Memory(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
            (n, ctypes.c_ulonglong) for n in ('total', 'available', 'page', 'apage',
                                             'virtual', 'avirtual', 'extended')]
    m = Memory()
    m.length = ctypes.sizeof(m)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        raise FlowError('HARDWARE', '无法读取内存信息。')
    model_dir = Path(os.environ.get('OLLAMA_MODELS', str(Path.home() / '.ollama' / 'models')))
    gpu = '未检测到；可使用 CPU（速度取决于设备）'
    try:
        p = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
             '[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); (Get-CimInstance Win32_VideoController).Name -join "; "'],
             capture_output=True, timeout=15, creationflags=0x08000000)
        gpu = p.stdout.decode('utf-8', errors='replace').strip() or gpu
    except (OSError, subprocess.TimeoutExpired):
        pass
    import sys
    return {'ram_gb': round(m.total / 2**30, 1),
            'available_gb': round(m.available / 2**30, 1),
            'model_free_gb': round(disk_free(model_dir), 1),
            'system_free_gb': round(disk_free(DATA), 1),
            'temp_free_gb': round(disk_free(os.environ.get('TEMP', str(DATA))), 1),
            'model_dir': str(model_dir), 'gpu': gpu, 'arch': platform.machine(),
            'windows_build': sys.getwindowsversion().build}


def recommend(hw):
    if hw['ram_gb'] >= 16 * .9 and hw['model_free_gb'] >= 10:
        return 'deepseek-r1:8b'
    if hw['ram_gb'] >= 8 * .9 and hw['model_free_gb'] >= 4:
        return 'deepseek-r1:1.5b'
    if hw['ram_gb'] < 6 * .9:
        return 'qwen2.5:0.5b'
    return 'qwen2.5:1.5b'


def request(path, payload=None, timeout=20):
    req = urllib.request.Request(LOCAL_URL + path,
         data=None if payload is None else json.dumps(payload).encode(),
         headers={'Content-Type': 'application/json'})
    # Loopback must never traverse a proxy.
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout)


def tags():
    with request('/api/tags') as r:
        return [m['name'] for m in json.load(r).get('models', [])]


def ollama_exe():
    if IS_MAC:
        from macos_support import mac_ollama_exe
        return mac_ollama_exe()
    candidate = shutil.which('ollama')
    if candidate:
        return candidate
    for base in (os.environ.get('LOCALAPPDATA', ''), os.environ.get('ProgramFiles', '')):
        for suffix in ('Programs/Ollama/ollama.exe', 'Ollama/ollama.exe'):
            p = Path(base) / suffix
            if p.is_file():
                return str(p)


def check_cancel(cancel):
    if cancel.is_set():
        raise FlowError('CANCELLED', '操作已取消；已下载的模型分块可在下次重试时复用。')


def ensure_engine(progress, cancel):
    try:
        tags()
        event('ENGINE_READY')
        return
    except Exception:
        pass
    if IS_MAC:
        from macos_support import ensure_mac_engine
        return ensure_mac_engine(progress, cancel)
    exe = ollama_exe()
    if not exe:
        progress('下载 Ollama 官方安装器（需要联网）…', 0)
        DATA.mkdir(parents=True, exist_ok=True)
        dest = DATA / 'OllamaSetup.exe'
        for attempt in range(3):
            check_cancel(cancel)
            try:
                with urllib.request.urlopen('https://ollama.com/download/OllamaSetup.exe', timeout=60) as r:
                    total = int(r.headers.get('Content-Length', 0))
                    count = 0
                    with dest.open('wb') as f:
                        while True:
                            check_cancel(cancel)
                            block = r.read(1024 * 1024)
                            if not block:
                                break
                            f.write(block)
                            count += len(block)
                            progress(f'Ollama 安装器 {count / 2**20:.1f} MB / '
                                     + (f'{total / 2**20:.1f} MB' if total else '总量未知'),
                                     count * 100 / total if total else 0)
                break
            except FlowError:
                raise
            except (OSError, ValueError):
                if attempt == 2:
                    raise FlowError('NETWORK', 'Ollama 下载失败。请检查网络后点击重试。') from None
                event('PULL_RETRY')
                cancel.wait(2 ** attempt)
        check_cancel(cancel)
        progress('验证 Ollama 安装器数字签名…', 0)
        ps = "$s=Get-AuthenticodeSignature -LiteralPath $env:RF_INSTALLER; if ($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -match 'Ollama') {exit 0} else {exit 1}"
        env = dict(os.environ, RF_INSTALLER=str(dest))
        try:
            valid = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', ps],
                      env=env, timeout=120, creationflags=0x08000000).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            valid = False
        if not valid:
            raise FlowError('SIGNATURE', 'Ollama 安装器签名验证失败；未运行。请检查网络和系统证书。')
        progress('正在安装 Ollama，请完成可能出现的官方安装窗口…', 0)
        p = subprocess.Popen([str(dest), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'])
        while p.poll() is None:
            # Do not forcibly terminate a dependency installer mid-transaction.
            time.sleep(.5)
        check_cancel(cancel)
        if p.returncode not in (0, 3010):
            raise FlowError('INSTALL', 'Ollama 安装未完成，请重试或从官网安装后重试。')
        exe = ollama_exe()
        if not exe:
            raise FlowError('INSTALL', '未找到 Ollama，请完成其安装后重试。')
    progress('启动本地 Ollama 服务…', 0)
    subprocess.Popen([exe, 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=0x08000000)
    for _ in range(60):
        check_cancel(cancel)
        try:
            tags()
            event('ENGINE_READY')
            return
        except Exception:
            cancel.wait(1)
    raise FlowError('NETWORK', 'Ollama 未能启动。检查 11434 端口及安全软件后重试。')


def provision(model, progress, cancel):
    if model not in MODELS:
        raise FlowError('HARDWARE', '请选择列表中的本地模型。')
    hw = hardware()
    if IS_MAC and (tuple(int(x) for x in hw['macos_version'].split('.')[:1]) < (14,)
                   or hw['arch'].lower() not in ('arm64', 'aarch64', 'x86_64')):
        raise FlowError('HARDWARE', '本地模式需要 macOS 14 或更新版本；本版优先支持 M 系列 Mac。')
    if not IS_MAC and (hw['windows_build'] < 19045 or hw['arch'].lower() not in ('amd64', 'x86_64')):
        raise FlowError('HARDWARE', '本 Beta 本地模式支持 Windows 10 22H2 / Windows 11 x64。')
    minimum_ram, disk = MODELS[model]
    # Firmware/integrated graphics reserve part of nominal installed RAM.
    if hw['ram_gb'] < minimum_ram * .9:
        raise FlowError('HARDWARE', '内存不足以推荐运行此模型，请选择更轻量模型或云端模式。')
    if not ollama_exe() and (hw['system_free_gb'] < 6 or hw['temp_free_gb'] < 3):
        raise FlowError('DISK', '安装 Ollama 需要系统盘至少 6 GiB、临时目录至少 3 GiB 可用空间。')
    ensure_engine(progress, cancel)
    installed = tags()
    if model not in installed:
        if hw['model_free_gb'] < disk:
            raise FlowError('DISK', f'模型目录空间不足，至少需要 {disk} GiB 可用空间。')
        for attempt in range(3):
            check_cancel(cancel)
            try:
                success = False
                with request('/api/pull', {'model': model, 'stream': True}, timeout=90) as r:
                    for line in r:
                        check_cancel(cancel)
                        item = json.loads(line)
                        if 'error' in item:
                            raise FlowError('NETWORK', '模型服务返回下载错误，请检查网络或稍后重试。')
                        total, done = item.get('total', 0), item.get('completed', 0)
                        progress('模型下载 / 验证：' + str(item.get('status', ''))[:120] +
                                 (f'  {done / 2**30:.2f}/{total / 2**30:.2f} GiB' if total else ''),
                                 done * 100 / total if total else 0)
                        success = item.get('status') == 'success'
                if not success:
                    raise FlowError('NETWORK', '下载流意外结束，请重试。')
                event('PULL_OK')
                break
            except Exception as e:
                if isinstance(e, FlowError) and e.code == 'CANCELLED':
                    raise
                if attempt == 2:
                    raise FlowError('NETWORK', '模型下载失败，已自动重试 3 次；可再次点击配置。') from None
                event('PULL_RETRY')
                progress(f'下载中断，准备第 {attempt + 2}/3 次尝试…', 0)
                cancel.wait(2 ** attempt)
    progress('执行真实推理检查（首次加载可能需要数分钟）…', 100)
    answer = infer({'mode': 'local', 'model': model}, 'Reply with the word READY.', '', cancel)
    if not answer.strip():
        raise FlowError('EMPTY', '模型返回空内容，联通检查失败。')
    progress('真实推理检查通过；可以开始翻译、润色、纠错、解释。', 100)


def clean_answer(text):
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S)
    if '<think>' in text:
        text = text.split('<think>')[0]
    return text.strip()


@lru_cache(maxsize=16)
def r1_fast_supported(model):
    if not model.startswith('deepseek-r1:'):
        return False
    try:
        with request('/api/show', {'model': model}, timeout=15) as r:
            details = json.load(r)
        template = details.get('template', '')
        # The old fast framing was verified on Qwen3-based R1 8B. Qwen2-based
        # R1 1.5B has similar marker strings but behaved incorrectly with it.
        return (model == 'deepseek-r1:8b'
                and details.get('model_info', {}).get('general.architecture') == 'qwen3'
                and all(token in template for token in ('<｜User｜>', '<｜Assistant｜>', '</think>', 'bos_token')))
    except Exception:
        return False


def local_payload(model, prompt):
    payload = {'model': model, 'prompt': prompt, 'stream': True,
               'options': {'num_ctx': 4096, 'num_predict': 2048, 'temperature': .2}}
    if r1_fast_supported(model):
        # Reuse the user's previously tested R1 fast-answer framing only after
        # checking the actual installed model template. Other models use theirs.
        payload.update(raw=True, prompt='<｜begin▁of▁sentence｜><｜User｜>' + prompt
                       + '<｜Assistant｜><think>\n\n</think>\n\n')
    return payload


def infer(config, prompt, key, cancel, on_text=None):
    check_cancel(cancel)
    text = ''
    try:
        if config['mode'] == 'cloud':
            url = normalize_base_url(config['cloud_url'])
            from urllib.parse import urlsplit
            parts = urlsplit(url)
            if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
                raise FlowError('HTTP', '云端地址必须为有效 HTTPS API 基础地址，不含用户名、查询参数或片段。')
            if not key.strip():
                raise FlowError('HTTP', '请输入云端 API Key；密钥仅保存在本次运行的内存中。')
            if not config.get('cloud_model', '').strip():
                raise FlowError('HTTP', '请填写供应商支持的实际模型 ID。')
            req = urllib.request.Request(url + '/chat/completions',
                data=json.dumps({'model': config['cloud_model'], 'stream': False,
                    'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 2048}).encode(),
                headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
            # Refuse redirects to avoid forwarding credentials to another host.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):
                    return None
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=180) as r:
                choice = json.load(r)['choices'][0]
                if choice.get('finish_reason') == 'length':
                    raise FlowError('LIMIT', '输出达到长度上限，请分段处理；未启用替换。')
                text = choice['message']['content']
        else:
            with request('/api/generate', local_payload(config['model'], prompt), timeout=180) as r:
                done = False
                for line in r:
                    check_cancel(cancel)
                    obj = json.loads(line)
                    if 'error' in obj:
                        raise FlowError('HTTP', '模型推理失败，请检查模型是否存在或重新配置。')
                    text += obj.get('response', '')
                    if on_text:
                        on_text(clean_answer(text))
                    done = obj.get('done', False)
                    if done and obj.get('done_reason') == 'length':
                        raise FlowError('LIMIT', '输出达到长度上限，请分段处理；未启用替换。')
                if not done:
                    raise FlowError('NETWORK', '推理连接意外中断，请重试。')
        check_cancel(cancel)
        text = clean_answer(text or '')
        if not text:
            raise FlowError('EMPTY', '模型没有返回可用正文，请重试或换用模型。')
        event('INFERENCE_OK')
        return text
    except FlowError:
        raise
    except urllib.error.HTTPError as e:
        raise FlowError('HTTP', f'请求失败（HTTP {e.code}）。检查模型名称、账户权限或服务地址。') from None
    except (OSError, urllib.error.URLError, TimeoutError):
        raise FlowError('NETWORK', '连接失败或超时；检查网络、Ollama 服务后重试。') from None
    except (ValueError, KeyError, TypeError, IndexError):
        raise FlowError('HTTP', '服务返回了无法识别的响应。') from None
