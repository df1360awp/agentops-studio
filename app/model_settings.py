"""Local-only model credential storage.

Windows encrypts the API key with user-scoped DPAPI. Other OSes use a
permission-restricted file (not strong encryption; see SECURITY.md).
This module never returns a secret to the browser or logs.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import re
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path
from urllib.parse import urlsplit


class _Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_byte))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    if sys.platform != 'win32':
        raise RuntimeError('DPAPI is only available on Windows')
    source = (ctypes.c_byte * len(data)).from_buffer_copy(data)
    src = _Blob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
    dst = _Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    func = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
    func.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    func.restype = wintypes.BOOL
    # 0x01: prohibit UI prompts. DPAPI keys are bound to the local Windows user.
    if not func(ctypes.byref(src), None, None, None, None, 0x01, ctypes.byref(dst)):
        raise RuntimeError('Windows DPAPI unavailable for current account')
    try:
        return ctypes.string_at(dst.pbData, dst.cbData)
    finally:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        kernel.LocalFree(ctypes.cast(dst.pbData, ctypes.c_void_p))


def _file() -> Path:
    override = os.environ.get('AGENTOPS_CONFIG_DIR')
    if override:
        root = Path(override)
    elif sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local')) / 'AgentOpsStudio'
    else:
        root = Path.home() / '.config' / 'agentops-studio'
    return root / 'model-settings.json'


def load() -> dict:
    path = _file()
    if not path.is_file():
        return {}
    obj = json.loads(path.read_text(encoding='utf-8'))
    if obj.get('encrypted') == 'win-dpapi':
        key = _dpapi(base64.b64decode(obj['api_key']), protect=False).decode('utf-8')
    elif obj.get('encrypted') == 'permissions-only' and sys.platform != 'win32':
        key = obj['api_key']
    else:
        raise RuntimeError('The local model settings are not readable by this account')
    return {'api_key': key, 'base_url': obj['base_url'], 'model': obj['model']}


def public() -> dict:
    obj = load()
    api_key = obj.get('api_key') or os.getenv('OPENAI_COMPAT_API_KEY') or os.getenv('OPENAI_API_KEY')
    return {
        'configured': bool(api_key),
        'has_key': bool(api_key),
        'key_mask': '已保存（不会回显）' if api_key else '尚未配置',
        'base_url': obj.get('base_url') or os.getenv('OPENAI_COMPAT_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
        'model': obj.get('model') or os.getenv('OPENAI_COMPAT_MODEL', 'qwen3.7-plus'),
        'storage': 'Windows DPAPI（本机用户加密）' if sys.platform == 'win32' else '本地受限权限文件',
    }


def credentials() -> tuple[str, str, str]:
    obj = load()
    return (
        obj.get('api_key') or os.getenv('OPENAI_COMPAT_API_KEY') or os.getenv('OPENAI_API_KEY', ''),
        obj.get('base_url') or os.getenv('OPENAI_COMPAT_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
        obj.get('model') or os.getenv('OPENAI_COMPAT_MODEL', 'qwen3.7-plus')
    )


def save(api_key: str, base_url: str, model: str) -> dict:
    existing = load()
    key = api_key.strip() if api_key else existing.get('api_key', '')
    if not key:
        raise ValueError('请粘贴API Key')
    if not 8 <= len(key) <= 512 or any(ch.isspace() for ch in key):
        raise ValueError('API Key 格式不正确')
    url = base_url.strip().rstrip('/')
    parsed = urlsplit(url)
    if len(url) > 600 or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('接口地址必须是有效的 HTTPS Base URL')
    if not re.fullmatch(r'[A-Za-z0-9._/-]{2,120}', model.strip()):
        raise ValueError('模型名称格式不正确')
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform != 'win32':
        os.chmod(path.parent, 0o700)
    payload = {
        'base_url': url, 'model': model.strip(),
        'api_key': base64.b64encode(_dpapi(key.encode('utf-8'), protect=True)).decode('ascii') if sys.platform == 'win32' else key,
        'encrypted': 'win-dpapi' if sys.platform == 'win32' else 'permissions-only'
    }
    fd, temp = tempfile.mkstemp(prefix='model-settings-', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(payload, out, ensure_ascii=False)
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return public()


def clear() -> dict:
    path = _file()
    path.unlink(missing_ok=True)
    return public()
