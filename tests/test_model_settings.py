"""Credential API guarantees: no echo, safe persistence, no model call on save."""
import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import model_settings, llm


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    monkeypatch.setenv('AGENTOPS_CONFIG_DIR', str(tmp_path / 'private-config'))
    monkeypatch.delenv('OPENAI_COMPAT_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('AGENTOPS_API_TOKEN', raising=False)


def test_save_get_and_delete_without_secret_echo():
    c = TestClient(app)
    secret = 'sk-test-local-only-very-secret-123456'
    assert not c.get('/api/model-settings').json()['has_key']
    r = c.post('/api/model-settings',json={'api_key':secret,
        'base_url':'https://example.aliyuncs.com/compatible-mode/v1',
        'model':'qwen3.7-plus'})
    assert r.status_code == 200
    assert secret not in r.text
    assert r.json()['configured']
    assert secret not in c.get('/api/model-settings').text
    assert secret not in c.get('/api/model-config').text
    assert secret not in c.get('/api/health').text
    assert model_settings.credentials()[0] == secret
    assert model_settings._file().is_file()
    if os.name != 'nt':
        assert model_settings._file().stat().st_mode & 0o077 == 0
    r = c.post('/api/model-settings',json={'api_key':'',
        'base_url':'https://example.aliyuncs.com/compatible-mode/v1',
        'model':'qwen4-max'})
    assert r.status_code == 200
    assert model_settings.credentials()[0] == secret
    assert model_settings.credentials()[2] == 'qwen4-max'
    assert c.delete('/api/model-settings').status_code == 200
    assert not c.get('/api/model-settings').json()['has_key']


def test_invalid_baseurl_and_key_not_stored():
    c=TestClient(app)
    for url in ('http://unsecured.example.com/v1','https://user:password@example.com/v1',
                'javascript:alert(1)','https://example.com/v1?token=secret'):
        r=c.post('/api/model-settings',json={'api_key':'sk-secret123','base_url':url,'model':'qwen3.7-plus'})
        assert r.status_code == 422
        assert not model_settings._file().exists()


def test_credential_management_is_local_only():
    from starlette.requests import Request
    from app.main import security_boundary
    import asyncio
    from starlette.responses import PlainTextResponse
    # A remote caller must never modify /api/model-settings, even if authenticated.
    scope={'type':'http','method':'POST','path':'/api/model-settings','root_path':'',
           'scheme':'http','server':('localhost',8766),'client':('203.0.113.20',5555),
           'headers':[], 'http_version':'1.1','query_string':b''}
    request=Request(scope)
    result=asyncio.run(security_boundary(request,lambda req:PlainTextResponse('yes')))
    assert result.status_code==403


def test_test_endpoint_calls_real_adapter_with_mocked_network(monkeypatch):
    c=TestClient(app)
    secret='sk-example-no-charge'
    c.post('/api/model-settings',json={'api_key':secret,'base_url':'https://example.aliyuncs.com/compatible-mode/v1','model':'qwen3.7-plus'})
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,*a):return json.dumps({'choices':[{'message':{'content':'连接成功'}}],
            'usage':{'prompt_tokens':12,'completion_tokens':3,'total_tokens':15}}).encode()
    def fake_urlopen(request, timeout):
        assert request.headers['Authorization'] == 'Bearer ' + secret
        assert request.full_url == 'https://example.aliyuncs.com/compatible-mode/v1/chat/completions'
        return Response()
    monkeypatch.setattr(llm.urllib.request,'urlopen',fake_urlopen)
    r=c.post('/api/model-settings/test')
    assert r.status_code==200 and r.json()['usage']['total_tokens']==15
    assert secret not in r.text


def test_broken_connection_never_exposes_secret(monkeypatch):
    c=TestClient(app)
    secret='sk-secret-dont-echo'
    c.post('/api/model-settings',json={'api_key':secret,'base_url':'https://example.aliyuncs.com/compatible-mode/v1','model':'qwen3.7-plus'})
    def failure(*args, **kwargs):raise RuntimeError('debug includes a secret: '+secret)
    monkeypatch.setattr(llm.urllib.request,'urlopen',failure)
    r=c.post('/api/model-settings/test')
    assert r.status_code==502 and secret not in r.text
