import json

import pytest
from fastapi.testclient import TestClient

from app import ai_workflows, llm, model_settings, store
from app.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "agentops-test.sqlite3")
    monkeypatch.setenv("AGENTOPS_CONFIG_DIR", str(tmp_path / "private-config"))
    monkeypatch.delenv("OPENAI_COMPAT_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENTOPS_API_TOKEN", raising=False)
    store.initialize()
    ai_workflows.initialize()
    model_settings.save(
        "sk-test-only-not-a-real-key",
        "https://example.aliyuncs.com/compatible-mode/v1",
        "qwen3.7-plus",
        "qwen3.5-plus-2026-02-15",
    )
    return TestClient(app)


def test_route_credentials_separate_complex_and_fast_models(client):
    _, _, complex_model = model_settings.route_credentials("complex")
    _, _, fast_model = model_settings.route_credentials("fast")
    assert complex_model == "qwen3.7-plus"
    assert fast_model == "qwen3.5-plus-2026-02-15"
    public = client.get("/api/model-settings").json()
    assert public["fast_model"] == fast_model
    assert "sk-test-only-not-a-real-key" not in json.dumps(public)


def test_ai_workflow_requires_explicit_external_processing_consent(client):
    response = client.post("/api/workflows/voc/ai-analyze", json={})
    assert response.status_code == 400
    assert "确认" in response.json()["detail"]


def test_voc_ai_analysis_uses_fast_route_and_excludes_raw_comments(client, monkeypatch):
    store.upsert_records(
        "feedback",
        [{
            "id": "VOC-TEST-01",
            "channel": "Web",
            "product": "Recorder",
            "market": "US",
            "rating": 1,
            "comment": "Sensitive customer email alice@example.com says export failed",
            "created_at": "2026-11-20",
        }],
    )
    captured = {}

    def fake_complete(question, context, route="complex"):
        captured["question"] = question
        captured["context"] = context
        captured["route"] = route
        return {
            "answer": "发现一条导出失败风险，建议人工复核。",
            "model": "qwen3.5-plus-2026-02-15",
            "route": route,
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }

    monkeypatch.setattr(llm, "complete_with_meta", fake_complete)
    response = client.post(
        "/api/workflows/voc/ai-analyze",
        json={"consent_to_external_processing": True, "route": "auto"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "fast"
    assert body["model"] == "qwen3.5-plus-2026-02-15"
    assert body["evidence_ids"] == ["VOC-TEST-01"]
    assert "alice@example.com" not in json.dumps(captured["context"])
    assert captured["route"] == "fast"
    saved = client.get("/api/ai-reports").json()
    assert saved[0]["id"] > 0
    assert saved[0]["answer"] == body["answer"]


def test_ceo_brief_ai_analysis_uses_complex_route(client, monkeypatch):
    seen = {}

    def fake_complete(question, context, route="complex"):
        seen["route"] = route
        return {
            "answer": "CEO简报分析",
            "model": "qwen3.7-plus",
            "route": route,
            "usage": {"total_tokens": 12},
        }

    monkeypatch.setattr(llm, "complete_with_meta", fake_complete)
    response = client.post(
        "/api/workflows/brief/ai-analyze",
        json={"consent_to_external_processing": True, "route": "auto"},
    )
    assert response.status_code == 200
    assert response.json()["route"] == "complex"
    assert seen["route"] == "complex"


def test_test_all_connections_calls_both_model_ids(client, monkeypatch):
    called = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, *args):
            return json.dumps({
                "choices": [{"message": {"content": "连接成功"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            }).encode("utf-8")

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        called.append(payload["model"])
        return FakeResponse()

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    response = client.post("/api/model-settings/test-all")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert called == ["qwen3.7-plus", "qwen3.5-plus-2026-02-15"]
