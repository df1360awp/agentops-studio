"""Tests for genuine offline processing and API. Uses isolated temporary database."""
import csv
import io
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app import store, engine
from app.main import app

@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv('AGENTOPS_SEED_SAMPLE','1')
    monkeypatch.delenv('AGENTOPS_API_TOKEN',raising=False)
    monkeypatch.setattr(store, 'DB_PATH', tmp_path/'test.db')
    store.initialize()


def test_initial_seed_is_fictional():
    o=store.get_overview()
    assert o['sample_data'] is True
    assert o['feedback_count']==15
    assert o['creator_count']==7
    assert o['roas']>0


def test_voc_prioritizes_file_loss():
    with store.connect() as db:result,steps,approvals=engine._voc(db)
    assert result['clusters'][0]['topic']=='数据丢失 / 导出异常'
    assert result['clusters'][0]['priority']=='P0'
    assert 'FB-001' in result['clusters'][0]['sample_ids']
    assert len(steps)==5
    assert len(approvals)>=1


def test_ads_computes_metrics_and_proposes_review_not_execution():
    with store.connect() as db:result,steps,approvals=engine._ads(db)
    assert result['campaign_count']==6
    assert len(approvals)>0
    assert any(x['roas']<1.8 and x['delta']==-.15 for x in result['details'])
    assert any(x['roas']>3.2 and x['delta']==.1 for x in result['details'])
    assert all('审批' in a['recommended_action'] or '审批' in result['rule'] for a in approvals)


def test_fraud_flag_reduces_creator_score():
    with store.connect() as db:result,steps,approvals=engine._kol(db)
    flagged=[x for x in result['scored'] if x['fraud_flag']]
    assert len(flagged)==1
    assert flagged[0]['score']<80
    assert all('报价' in a['detail'] for a in approvals)


def test_workflow_api_approvals_and_brief():
    c=TestClient(app)
    for slug in ('voc','ads','kol','brief'):
        r=c.post(f'/api/workflows/{slug}/run')
        assert r.status_code==200
        assert r.json()['status']=='completed'
        assert len(r.json()['steps'])==5
    a=c.get('/api/approvals').json()
    assert len(a)>=3
    assert a[0]['status']=='pending'
    decision=c.post(f'/api/approvals/{a[0]["id"]}/decision',json={'decision':'approved','comment':'面试演示审批'})
    assert decision.status_code==200
    assert decision.json()['status']=='approved'
    assert c.post(f'/api/approvals/{a[0]["id"]}/decision',json={'decision':'rejected'}).status_code==409
    brief=c.get('/api/brief.md')
    assert brief.status_code==200
    assert '原始记录' in brief.text
    assert '虚构' in brief.text
    assert c.post('/api/reset').json()['ok'] is True
    assert c.get('/api/overview').json()['pending_approvals']==0


def test_csv_import_and_validation():
    c=TestClient(app)
    fixture=store.export_csv('feedback')
    assert 'FB-001' in fixture
    r=c.post('/api/datasets/feedback/import',files={'file':('feedback.csv',fixture.encode('utf-8'),'text/csv')})
    assert r.status_code==200
    assert r.json()['accepted']==15
    broken='id,channel,product,market,rating,comment,created_at\nFB-BAD,web,prod,US,8,invalid,2026-11-19\n'
    r=c.post('/api/datasets/feedback/import',files={'file':('bad.csv',broken.encode(),'text/csv')})
    assert r.status_code==422


def test_offline_copilot_real_question():
    c=TestClient(app)
    r=c.post('/api/copilot',json={'question':'哪些广告应该调整预算？','mode':'rules'})
    assert r.status_code==200
    assert r.json()['mode']=='offline_rules'
    assert 'ROAS' in r.json()['answer']
    assert c.get('/api/model-config').json()['model']


def test_unknown_workflow_is_rejected():
    c=TestClient(app)
    assert c.post('/api/workflows/unknown/run').status_code==404
