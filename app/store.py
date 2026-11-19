"""SQLite storage for imported business datasets; optional explicit sample fixtures."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get('AGENTOPS_DB_PATH', os.environ.get('AgentOps_DB_PATH', BASE / 'data' / 'studio.sqlite3')))
VALID_TABLES = {'feedback', 'campaigns', 'creators'}
FIELDS = {
    'feedback': ['id', 'channel', 'product', 'market', 'rating', 'comment', 'created_at'],
    'campaigns': ['id', 'channel', 'name', 'market', 'spend', 'impressions', 'clicks', 'conversions', 'revenue'],
    'creators': ['id', 'handle', 'channel', 'market', 'followers', 'engagement', 'brand_fit', 'fee', 'fraud_flag']
}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    return conn


def dicts(rows):
    return [dict(r) for r in rows]


def initialize():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS feedback (
            id TEXT PRIMARY KEY, channel TEXT NOT NULL, product TEXT NOT NULL,
            market TEXT NOT NULL, rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS campaigns (
            id TEXT PRIMARY KEY, channel TEXT NOT NULL, name TEXT NOT NULL,
            market TEXT NOT NULL, spend REAL NOT NULL CHECK(spend >= 0),
            impressions INTEGER NOT NULL CHECK(impressions >= 0),
            clicks INTEGER NOT NULL CHECK(clicks >= 0),
            conversions INTEGER NOT NULL CHECK(conversions >= 0),
            revenue REAL NOT NULL CHECK(revenue >= 0)
        );
        CREATE TABLE IF NOT EXISTS creators (
            id TEXT PRIMARY KEY, handle TEXT NOT NULL, channel TEXT NOT NULL,
            market TEXT NOT NULL, followers INTEGER NOT NULL,
            engagement REAL NOT NULL, brand_fit REAL NOT NULL,
            fee REAL NOT NULL, fraud_flag INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, workflow TEXT NOT NULL,
            started_at TEXT NOT NULL, status TEXT NOT NULL,
            steps_json TEXT NOT NULL, result_json TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'rules'
        );
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL,
            kind TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL,
            recommended_action TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL, decided_at TEXT,
            comment TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (run_id) REFERENCES runs(id)
        );
        CREATE TABLE IF NOT EXISTS knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            section TEXT NOT NULL, body TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approval_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, approval_id INTEGER NOT NULL,
            action TEXT NOT NULL, actor TEXT NOT NULL, comment TEXT NOT NULL,
            timestamp TEXT NOT NULL, FOREIGN KEY (approval_id) REFERENCES approvals(id)
        );
        CREATE INDEX IF NOT EXISTS idx_runs_time ON runs(started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
        ''')
        if 'input_hash' not in [row[1] for row in db.execute('PRAGMA table_info(runs)')]:
            db.execute('ALTER TABLE runs ADD COLUMN input_hash TEXT')
        if os.getenv('AGENTOPS_SEED_SAMPLE','0') == '1' and db.execute('SELECT COUNT(*) FROM feedback').fetchone()[0] == 0:
            _seed(db)


def _seed(db):
    # Fictional records solely for interview demonstration; no real customer data.
    feedback = [
        ('FB-001','Shopify','CreatorAudio S1','US',2,'Recording export froze twice and I lost my project file.'),
        ('FB-002','TikTok Shop','CreatorAudio S1','US',1,'My recorded audio disappears after saving the session.'),
        ('FB-003','Amazon','CreatorAudio S1','US',2,'Export WAV file failed after the latest firmware update.'),
        ('FB-004','Website','CreatorAudio S1','UK',2,'Bluetooth pairing is confusing. Setup took nearly one hour.'),
        ('FB-005','TikTok Shop','CreatorAudio S1','US',3,'I cannot connect bluetooth with my phone on the first attempt.'),
        ('FB-006','Amazon','CreatorAudio S1','DE',4,'Amazing sound, shipping took a little longer than expected.'),
        ('FB-007','Shopify','CreatorAudio S1','US',5,'Great product; fast setup and a clean recording sound.'),
        ('FB-008','Website','CreatorAudio S1','US',2,'No clear onboarding guide. Need step-by-step setup instructions.'),
        ('FB-009','TikTok Shop','CreatorAudio S1','CA',5,'Love the portable studio. Creator workflow is much faster.'),
        ('FB-010','Amazon','CreatorAudio S1','US',3,'Package delayed by seven days. Tracking information was unclear.'),
        ('FB-011','Shopify','CreatorAudio S1','US',2,'The app crashed before I could export my voice memo.'),
        ('FB-012','Website','CreatorAudio S1','US',4,'Nice interface, but the subscription pricing needs clarification.'),
        ('FB-013','TikTok Shop','CreatorAudio S1','US',2,'Audio file failed to save; can the team recover my project?'),
        ('FB-014','Shopify','CreatorAudio S1','UK',5,'Perfect companion for field recording.'),
        ('FB-015','Amazon','CreatorAudio S1','US',3,'Missing USB cable, but customer service replied.'),
    ]
    t = datetime.now(timezone.utc)
    for i,(fid,ch,product,market,rating,comment) in enumerate(feedback):
        db.execute('INSERT INTO feedback VALUES (?,?,?,?,?,?,?)', (fid,ch,product,market,rating,comment,(t-timedelta(hours=3*i)).replace(microsecond=0).isoformat()))
    campaigns = [
        ('AD-001','Meta','US · Creator Conversion','US',4850,162000,4820,162,14580),
        ('AD-002','TikTok','US · UGC Discovery','US',3900,205000,6600,111,5850),
        ('AD-003','Google','Search · Branded Intent','US',2120,84000,3180,174,12140),
        ('AD-004','Meta','UK · Lookalike Test','UK',2800,99000,2670,63,4095),
        ('AD-005','TikTok','CA · Creator Spark','CA',1450,78000,2960,72,5100),
        ('AD-006','Meta','DE · Awareness Test','DE',1100,65000,980,18,1050),
    ]
    db.executemany('INSERT INTO campaigns VALUES (?,?,?,?,?,?,?,?,?)', campaigns)
    creators = [
        ('KOL-01','@echoeswithmia','TikTok','US',158000,5.8,94,1800,0),
        ('KOL-02','@soundbyjames','YouTube','US',81000,7.2,91,1250,0),
        ('KOL-03','@studio_minute','Instagram','UK',64000,4.9,88,900,0),
        ('KOL-04','@viral_everyday','TikTok','US',690000,0.9,62,8500,1),
        ('KOL-05','@maker_june','TikTok','CA',36000,6.1,85,600,0),
        ('KOL-06','@musicplanet','YouTube','DE',230000,2.2,78,3500,0),
        ('KOL-07','@audiojournal','Instagram','US',48000,4.8,92,1050,0),
    ]
    db.executemany('INSERT INTO creators VALUES (?,?,?,?,?,?,?,?,?)', creators)
    know = [
        ('品牌定位','brand','AgentOps 音乐创作科技业务演示。示例产品 CreatorAudio S1 面向个人创作者与轻量录音。所有市场数据和产品参数均为虚构样例，不代表 AgentOps 实际经营情况。'),
        ('VOC处理SOP','support','用户反馈按照数据采集→主题分类→风险排序→人工确认→问题反馈→复盘推进。严重录音丢失问题应优先人工核查，未确认前不直接自动回复承诺补偿。'),
        ('投放预算安全规则','ads','ROAS 低于 1.8 时建议调低预算；ROAS 高于 3.2 且至少有20单转化时可建议试探性增加预算。所有预算调整在人工审批前不得同步到广告平台。'),
        ('达人合作合规','kol','对KOL评分综合品牌匹配度、真实互动率、报价与疑似异常指标。达人触达、合同与付款需人工审核。分数只是规则排序，不代表真实转化效果预测。'),
        ('指标口径','analytics','ROAS=归因营收/广告花费，CPA=广告花费/订单转化数，CTR=点击/曝光，CVR=订单转化数/点击。归因可能存在平台差异，不能把数据样例当作因果增量。'),
        ('自动化边界','safety','可自动化：CSV读取、标准化、关键词分类、规则排序、草稿生成和日报。必须人工参与：预算更改、公开回复、达人发送、合同付款、重大缺陷判断。'),
    ]
    db.executemany('INSERT INTO knowledge(title,section,body) VALUES (?,?,?)',know)


def reset():
    with connect() as db:
        for table in ('approval_events','approvals','runs','feedback','campaigns','creators','knowledge'):
            db.execute(f'DELETE FROM {table}')
        if os.getenv('AGENTOPS_SEED_SAMPLE','0') == '1':
            _seed(db)


def table_rows(name):
    if name not in VALID_TABLES:
        raise ValueError('Unknown dataset')
    with connect() as db:
        return dicts(db.execute(f'SELECT * FROM {name} ORDER BY id').fetchall())


def get_overview():
    with connect() as db:
        f=db.execute('SELECT COUNT(*), SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END) FROM feedback').fetchone()
        s=db.execute('SELECT COALESCE(SUM(spend),0), COALESCE(SUM(revenue),0), COALESCE(SUM(conversions),0) FROM campaigns').fetchone()
        c=db.execute('SELECT COUNT(*) FROM creators').fetchone()[0]
        a=db.execute("SELECT COUNT(*) FROM approvals WHERE status='pending'").fetchone()[0]
        r=db.execute('SELECT COUNT(*) FROM runs').fetchone()[0]
        runs=dicts(db.execute('SELECT id,workflow,started_at,status,mode FROM runs ORDER BY id DESC LIMIT 8').fetchall())
        return {'feedback_count':f[0], 'negative_feedback':f[1] or 0,
                'spend':round(s[0],2), 'revenue':round(s[1],2),
                'roas':round(s[1]/s[0],2) if s[0] else 0, 'conversions':s[2],
                'creator_count':c, 'pending_approvals':a,'run_count':r,
                'latest_runs':runs,'sample_data':os.getenv('AGENTOPS_SEED_SAMPLE','0') == '1','brand':'AgentOps Studio'}


def get_runs(limit=25):
    with connect() as db:
        rows=dicts(db.execute('SELECT * FROM runs ORDER BY id DESC LIMIT ?', (min(max(1,limit),100),)).fetchall())
    for row in rows:
        row['steps']=json.loads(row.pop('steps_json'))
        row['result']=json.loads(row.pop('result_json'))
    return rows


def get_approvals():
    with connect() as db:
        return dicts(db.execute('SELECT a.*,r.workflow FROM approvals a JOIN runs r ON a.run_id=r.id ORDER BY CASE a.status WHEN "pending" THEN 0 ELSE 1 END, a.id DESC').fetchall())


def set_approval(approval_id, decision, comment=''):
    if decision not in ('approved','rejected'):
        raise ValueError('decision must be approved or rejected')
    with connect() as db:
        row=db.execute('SELECT * FROM approvals WHERE id=?',(approval_id,)).fetchone()
        if row is None:
            return None
        if row['status'] != 'pending':
            raise ValueError('This approval was already decided')
        now=utc_now()
        update=db.execute("UPDATE approvals SET status=?,comment=?,decided_at=? WHERE id=? AND status='pending'",
                          (decision,comment[:500],now,approval_id))
        if update.rowcount != 1:
            raise ValueError('Another reviewer already decided this approval')
        db.execute('INSERT INTO approval_events(approval_id,action,actor,comment,timestamp) VALUES(?,?,?,?,?)',
                   (approval_id,decision,'authenticated_operator',comment[:500],now))
        return dict(db.execute('SELECT * FROM approvals WHERE id=?',(approval_id,)).fetchone())


def import_csv(dataset, raw: bytes):
    if dataset not in VALID_TABLES:
        raise ValueError('Unknown dataset')
    if len(raw)>1024*1024:
        raise ValueError('CSV must be 1 MB or smaller')
    try:
        text=raw.decode('utf-8-sig')
    except UnicodeError:
        raise ValueError('CSV must be UTF-8 encoded')
    rdr=csv.DictReader(io.StringIO(text))
    required=FIELDS[dataset]
    if not rdr.fieldnames or any(col not in rdr.fieldnames for col in required):
        raise ValueError('Required CSV columns: '+', '.join(required))
    rows=list(rdr)
    if len(rows)>500:
        raise ValueError('Maximum 500 records per import')
    if not rows:
        raise ValueError('CSV has no data rows')
    clean=[]
    number_cols={'feedback':{'rating':int},'campaigns':{'spend':float,'impressions':int,'clicks':int,'conversions':int,'revenue':float},'creators':{'followers':int,'engagement':float,'brand_fit':float,'fee':float,'fraud_flag':int}}[dataset]
    for n,row in enumerate(rows,2):
        obj={k:(row.get(k) or '').strip()[:1500] for k in required}
        if not obj['id'] or any(not obj[k] for k in required if k not in number_cols):
            raise ValueError(f'Row {n}: missing value')
        try:
            for key,func in number_cols.items():
                obj[key]=func(obj[key])
        except (ValueError,TypeError):
            raise ValueError(f'Row {n}: invalid numeric value')
        if dataset=='feedback' and not 1<=obj['rating']<=5:
            raise ValueError(f'Row {n}: rating must be 1-5')
        if any(not math.isfinite(float(obj[k])) for k in number_cols):
            raise ValueError(f'Row {n}: numeric values must be finite')
        if any(obj[k]<0 for k in number_cols):
            raise ValueError(f'Row {n}: negative numeric value')
        if dataset=='campaigns' and (obj['clicks']>obj['impressions'] or obj['conversions']>obj['clicks']):
            raise ValueError(f'Row {n}: conversions <= clicks <= impressions is required')
        if dataset=='creators' and (obj['brand_fit']>100 or obj['engagement']>100 or obj['fraud_flag'] not in (0,1)):
            raise ValueError(f'Row {n}: creator scores out of range')
        clean.append([obj[k] for k in required])
    # Validate all records BEFORE opening the transaction; a failed import writes nothing.
    with connect() as db:
        for row in clean:
            db.execute(f'INSERT OR REPLACE INTO {dataset}({",".join(required)}) VALUES ({",".join("?" for _ in required)})', row)
    return {'dataset':dataset,'accepted':len(clean),'count_total':len(table_rows(dataset))}


def export_csv(dataset):
    if dataset not in VALID_TABLES:
        raise ValueError('Unknown dataset')
    sio=io.StringIO()
    out=csv.DictWriter(sio,fieldnames=FIELDS[dataset])
    out.writeheader()
    for record in table_rows(dataset):
        # Guard spreadsheet users against formula injection from untrusted imported text.
        safe={k:("'"+str(v) if isinstance(v,str) and v.startswith(('=', '+', '-', '@')) else v)
              for k,v in record.items()}
        out.writerow(safe)
    return sio.getvalue()



def get_approval_events(limit: int=100):
    with connect() as db:
        return dicts(db.execute('SELECT * FROM approval_events ORDER BY id DESC LIMIT ?',
                                (min(max(limit,1),1000),)).fetchall())


def input_fingerprint(db, workflow: str) -> str:
    """Re-run a workflow only when its input snapshot changes, by default."""
    dataset_map={'voc':['feedback'],'ads':['campaigns'],'kol':['creators'],
                 'brief':['feedback','campaigns','creators']}
    tables=dataset_map[workflow]
    snapshot={name:dicts(db.execute(f'SELECT * FROM {name} ORDER BY id').fetchall())
              for name in tables}
    raw=json.dumps({'workflow':workflow,'rule_version':2,'tables':snapshot},
                   ensure_ascii=False,sort_keys=True,default=str).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def upsert_records(dataset: str, records: list[dict]):
    """Import JSON records using the same validation as CSV (transactional)."""
    if dataset not in VALID_TABLES: raise ValueError('Unknown dataset')
    if not records: raise ValueError('Provide at least one record')
    if len(records)>500: raise ValueError('Maximum 500 records per request')
    output=io.StringIO()
    writer=csv.DictWriter(output,fieldnames=FIELDS[dataset],extrasaction='ignore')
    writer.writeheader()
    for item in records:
        if not isinstance(item,dict): raise ValueError('Every record must be a JSON object')
        writer.writerow(item)
    return import_csv(dataset,output.getvalue().encode('utf-8'))
