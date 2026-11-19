"""Optional OpenAI-compatible model adapter. Never called unless user opts in."""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request
from . import model_settings


def settings():
    info = model_settings.public()
    return {'configured': info['configured'], 'model': info['model'], 'base_url': info['base_url']}


def _request(key: str, url: str, model: str, messages: list, max_tokens: int):
    endpoint = url.rstrip('/') + '/chat/completions'
    payload = json.dumps({'model': model, 'messages': messages,
                          'temperature': 0.2, 'max_tokens': max_tokens},
                         ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(endpoint, data=payload, headers={
        'Authorization': 'Bearer ' + key,
        'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read(1024 * 1024))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'模型服务返回 HTTP {e.code}，请检查模型、额度、接口地址或密钥。')
    except Exception:
        raise RuntimeError('模型连接失败。请检查网络和接口地址。')
    try:
        content = result['choices'][0]['message']['content']
        if not isinstance(content, str):
            raise ValueError('content not text')
    except (KeyError, IndexError, TypeError, ValueError):
        raise RuntimeError('接口未返回兼容的模型文本内容')
    return content, result.get('usage') or {}


def test_connection():
    key, url, model = model_settings.credentials()
    if not key:
        raise RuntimeError('请先保存 API Key')
    answer, usage = _request(key, url, model, [
        {'role': 'user', 'content': '这是接口连通性测试。请仅回复：连接成功'}
    ], max_tokens=48)
    # Return only connection result and token usage; never the key or raw request.
    return {'ok': True, 'model': model, 'reply': answer[:180],
            'usage': {k: v for k, v in usage.items() if k in (
                'prompt_tokens', 'completion_tokens', 'total_tokens') and isinstance(v, int)}}


def complete(question, context):
    key, url, model = model_settings.credentials()
    if not key:
        raise RuntimeError('未设置API Key，请在「模型设置」中保存密钥。')
    system = """你是为运营数据辅助决策的工作流分析助手。必须只使用给定数据推导结论，不编造经营绩效或市场事件。
优先引用原始记录ID，区分事实、规则建议和推断。涉及投放调价、客户消息或合同必须人工审批。"""
    answer, _ = _request(key, url, model, [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': '业务数据摘要：\n' + json.dumps(context, ensure_ascii=False)[:12000]
         + '\n\n问题：' + question[:500]}
    ], max_tokens=550)
    return answer
