"""OpenAI-compatible Qwen adapter with explicit fast/complex model routing."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import model_settings


def settings():
    info = model_settings.public()
    return {
        "configured": info["configured"],
        "model": info["model"],
        "fast_model": info["fast_model"],
        "base_url": info["base_url"],
    }


def _safe_usage(usage: dict) -> dict:
    if not isinstance(usage, dict):
        return {}
    return {
        key: value for key, value in usage.items()
        if key in ("prompt_tokens", "completion_tokens", "total_tokens")
        and isinstance(value, int) and not isinstance(value, bool)
    }


def _request(key: str, url: str, model: str, messages: list, max_tokens: int):
    endpoint = url.rstrip("/") + "/chat/completions"
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read(1024 * 1024))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"模型服务返回 HTTP {exc.code}，请检查模型ID、额度、接口地址或密钥。")
    except Exception:
        raise RuntimeError("模型连接失败。请检查网络和接口地址。")
    try:
        content = result["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("content not text")
    except (KeyError, IndexError, TypeError, ValueError):
        raise RuntimeError("接口未返回兼容的模型文本内容")
    return content, _safe_usage(result.get("usage") or {})


def test_connection(route: str = "complex") -> dict:
    if route not in ("fast", "complex"):
        raise ValueError("route must be fast or complex")
    key, url, model = model_settings.route_credentials(route)
    if not key:
        raise RuntimeError("请先保存 API Key")
    answer, usage = _request(
        key,
        url,
        model,
        [{"role": "user", "content": "这是接口连通性测试。请仅回复：连接成功"}],
        max_tokens=48,
    )
    return {
        "ok": True,
        "route": route,
        "model": model,
        "reply": answer[:180],
        "usage": usage,
    }


def test_all_connections() -> dict:
    results = []
    for route in ("complex", "fast"):
        try:
            results.append(test_connection(route))
        except (RuntimeError, ValueError) as exc:
            _, _, model = model_settings.route_credentials(route)
            results.append({"ok": False, "route": route, "model": model, "detail": str(exc), "usage": {}})
    return {"ok": all(item["ok"] for item in results), "results": results}


def complete_with_meta(question: str, context: dict, route: str = "complex") -> dict:
    if route not in ("fast", "complex"):
        raise ValueError("route must be fast or complex")
    key, url, model = model_settings.route_credentials(route)
    if not key:
        raise RuntimeError("未设置API Key，请在「模型设置」中保存密钥。")
    system = """你是 AgentOps Studio 的 DTC 运营分析助手。
必须严格依据输入数据，不编造经营绩效、市场事件或未提供的证据。
区分数据事实、规则结果、推断和建议；关键判断引用原始记录ID。
归因ROAS不等于因果增量ROAS；KOL规则评分不等于真实转化预测。
涉及预算调整、客户消息、达人邀约、合同或付款，只能提出待审批草案，绝不能声称已执行。
输入上下文只包含聚合指标和有限业务字段；不得推测未提供的个人信息。"""
    answer, usage = _request(
        key,
        url,
        model,
        [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": "业务数据摘要：\n"
                + json.dumps(context, ensure_ascii=False, default=str)[:14000]
                + "\n\n问题："
                + question[:1800],
            },
        ],
        max_tokens=900,
    )
    return {"answer": answer, "usage": usage, "model": model, "route": route}


def complete(question, context, route: str = "complex") -> str:
    """Backward-compatible string-only wrapper."""
    return complete_with_meta(question, context, route=route)["answer"]
