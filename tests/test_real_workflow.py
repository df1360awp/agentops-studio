"""Regression tests for secure default, real ingestion, idempotency and audit."""
import csv
import io
import pytest
from fastapi.testclient import TestClient
from app import store
from app.main import app


@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'DB_PATH',tmp_path/'isolated.sqlite3')
    monkeypatch.delenv('AGENTOPS_SEED_SAMPLE',raising=False)
    monkeypatch.delenv('AGENTOPS_API_TOKEN',raising=False)
    store.initialize()


def test_empty_database_by_default_and_real_csv():
    c=TestClient(app)
    o=c.get('/api/overview').json()
    assert o['feedback_count']==0 and o['sample_data'] is False
    assert o['roas']==0 and o['pending_approvals']==0
    # Real, independently supplied data drives results rather than hardcoded fixture metrics.
    dataset='id,channel,name,market,spend,impressions,clicks,conversions,revenue\nREAL1,Meta,CampaignA,US,100,1000,200,10,400\n'
    r=c.post('/api/datasets/campaigns/import',files={'file':('metrics.csv',dataset.encode(),'text/csv')})
    assert r.status_code==200
    assert c.get('/api/overview').json()['roas']==4.0
    ads=c.post('/api/workflows/ads/run').json()
    assert ads['result']['details'][0]['id']=='REAL1'
    assert ads['result']['details'][0]['roas']==4.0


def test_idempotency_reuses_same_inputs_and_recomputes_updated_data():
    c=TestClient(app)
    first=c.post('/api/workflows/voc/run').json()
    assert first['status']=='completed'
    assert c.post('/api/workflows/voc/run').json()['status']=='cached'
    assert c.get('/api/overview').json()['run_count']==1
    r=c.post('/api/datasets/feedback/ingest',json=[{'id':'A','channel':'Store','product':'Audio',
        'market':'US','rating':1,'comment':'Failed to export my recording',
        'created_at':'2026-11-19T00:00:00+00:00'}])
    assert r.status_code==200
    nxt=c.post('/api/workflows/voc/run').json()
    assert nxt['status']=='completed' and nxt['approvals_created']>=1
    assert nxt['result']['count']==1
    assert c.get('/api/overview').json()['run_count']==2
    assert c.post('/api/workflows/voc/run?force=true').json()['status']=='completed'


def test_api_auth_local_key_and_approval_audit(monkeypatch):
    monkeypatch.setenv('AGENTOPS_API_TOKEN','a-super-secret-local-token')
    c=TestClient(app)
    assert c.get('/api/health').status_code==200
    assert c.post('/api/workflows/run-all').status_code==401
    h={'Authorization':'Bearer a-super-secret-local-token'}
    assert c.get('/api/overview',headers=h).status_code==200
    assert c.post('/api/datasets/feedback/ingest',json=[{'id':'B','channel':'Web','product':'Audio','market':'US',
      'rating':1,'comment':'File lost during saving','created_at':'2026-11-19'}],headers=h).status_code==200
    first=c.post('/api/workflows/voc/run',headers=h).json()
    assert first['approvals_created']>=1
    approvals=c.get('/api/approvals',headers=h).json()
    changed=c.post(f'/api/approvals/{approvals[0]["id"]}/decision',headers=h,
                   json={'decision':'rejected','comment':'Need additional evidence'})
    assert changed.status_code==200
    audit=c.get('/api/approval-events',headers=h).json()
    assert len(audit)==1 and audit[0]['action']=='rejected'
    assert c.post(f'/api/approvals/{approvals[0]["id"]}/decision',headers=h,
                   json={'decision':'approved'}).status_code==409


def test_bad_analytics_csv_is_atomic():
    c=TestClient(app)
    bad='id,channel,name,market,spend,impressions,clicks,conversions,revenue\nA,Meta,Ad,US,10,100,500,3,20\n'
    assert c.post('/api/datasets/campaigns/import',files={'file':('x.csv',bad.encode())}).status_code==422
    assert c.get('/api/datasets/campaigns').json()==[]


def test_export_formula_neutralization():
    store.upsert_records('feedback',[{'id':'GOOD','channel':'Web','product':'Audio','market':'US',
        'rating':2,'comment':'=1+2','created_at':'2026-11-19'}])
    exported=store.export_csv('feedback')
    assert "'=1+2" in exported


def test_api_csrf_origin_rejection():
    c=TestClient(app)
    assert c.post('/api/workflows/voc/run',headers={'Origin':'https://example.com'}).status_code==403
