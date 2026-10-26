"""Reviewed provider examples and approximate Ollama model weight sizes, 2026-10-25."""
PROVIDERS = {
    'DeepSeek 官方': ('https://api.deepseek.com', ('deepseek-flash', 'deepseek-v4-pro')),
    '阿里云百炼 · 北京': ('https://dashscope.aliyuncs.com/compatible-mode/v1', ('qwen-plus', 'qwen-turbo')),
    '阿里云百炼 · 新加坡': ('https://dashscope-intl.aliyuncs.com/compatible-mode/v1', ('qwen-plus', 'qwen-turbo')),
    '硅基流动 SiliconFlow': ('https://api.siliconflow.cn/v1', ('deepseek-ai/DeepSeek-V4-Flash',)),
    '月之暗面 Kimi · 国内': ('https://api.moonshot.cn/v1', ('kimi-k3.1-pro',)),
    '自定义（兼容 Chat Completions）': ('', ()),
}
CUSTOM_PROVIDER = list(PROVIDERS)[-1]
# RAM and reserved free disk are conservative heuristics, separate from weight size.
MODEL_CATALOG = {
    'deepseek-r1:1.5b': (8, 4, '1.1 GB'),
    'deepseek-r1:7b': (16, 9, '4.7 GB'),
    'deepseek-r1:8b': (16, 10, '5.2 GB'),
    'deepseek-r1:14b': (32, 18, '9.0 GB'),
    'qwen2.5:0.5b': (4, 2, '398 MB'),
    'qwen2.5:1.5b': (6, 4, '986 MB'),
    'qwen2.5:3b': (8, 5, '1.9 GB'),
    'qwen2.5:7b': (16, 9, '4.7 GB'),
    'llama3.2:1b': (6, 4, '1.3 GB'),
    'llama3.2:3b': (8, 5, '2.0 GB'),
}
MODEL_LABELS = {name: f'{name}  ·  约 {spec[2]}' for name, spec in MODEL_CATALOG.items()}
LABEL_TO_MODEL = {label: name for name, label in MODEL_LABELS.items()}


def provider_for_url(url):
    for name, (base, models) in PROVIDERS.items():
        if base and url.rstrip('/') == base:
            return name
    if url.rstrip('/') == 'https://api.deepseek.com/v1':
        return 'DeepSeek 官方'
    return CUSTOM_PROVIDER


def normalize_base_url(url):
    url = url.strip().rstrip('/')
    suffix = '/chat/completions'
    if url.endswith(suffix):
        url = url[:-len(suffix)].rstrip('/')
    return url
