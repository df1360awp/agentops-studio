"""HTTP API and static dashboard for independent AgentOps Studio."""
from __future__ import annotations
import io
import os
import hmac
from urllib.parse import urlparse
import json
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, File, UploadFile, Body, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import store, engine, llm, model_settings, ai_workflows

store.initialize()
ai_workflows.initialize()
ROOT=Path(__file__).resolve().parents[1]
app=FastAPI(title='AgentOps Studio',description='Evidence-traceable DTC operations with real CSV/JSON ingestion and human approval.',version='2.1.0')

# Without an API token the application is strictly local-only. For network access,
# set AGENTOPS_API_TOKEN to a strong random secret and use TLS in front of Uvicorn.
@app.middleware('http')
async def security_boundary(request: Request, call_next):
    if request.url.path.startswith('/api/model-settings'):
        # Credential management is always localhost-only, even with an API token.
        if not request.client or request.client.host not in ('127.0.0.1','::1','testclient'):
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail':'模型密钥管理仅限本机访问'},status_code=403)
    if request.url.path.startswith('/api/') and request.url.path not in ('/api/health','/api/model-config'):
        token=os.environ.get('AGENTOPS_API_TOKEN','')
        if token:
            candidate=request.headers.get('Authorization','')
            if not hmac.compare_digest(candidate,'Bearer '+token):
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail':'API authentication required'},status_code=401)
        elif request.client and request.client.host not in ('127.0.0.1','::1','testclient') and not (
            os.getenv('AGENTOPS_LOCAL_CONTAINER','0')=='1' and request.url.hostname in ('localhost','127.0.0.1')
        ):
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail':'Local-only mode. Configure AGENTOPS_API_TOKEN for remote access.'},status_code=403)
        if request.method in ('POST','PUT','PATCH','DELETE'):
            origin=request.headers.get('Origin')
            if origin and urlparse(origin).netloc != request.url.netloc:
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail':'Cross-origin write rejected'},status_code=403)
    return await call_next(request)

class ApprovalDecision(BaseModel):
    decision: Literal['approved','rejected']
    comment: str=Field(default='',max_length=500)

class ModelSettingsInput(BaseModel):
    api_key: str = Field(default='', max_length=512)
    base_url: str = Field(min_length=10, max_length=600)
    model: str = Field(min_length=2, max_length=120)
    fast_model: str = Field(default='qwen3.5-plus-2026-02-15', min_length=2, max_length=120)


class ChatRequest(BaseModel):
    question: str=Field(min_length=1,max_length=500)
    mode: Literal["rules","llm"]="rules"
    route: Literal["fast","complex"]="complex"


class AIWorkflowRequest(BaseModel):
    consent_to_external_processing: bool = False
    force: bool = False
    route: Literal["auto","fast","complex"] = "auto"

@app.get('/api/health')
def health():
    return {'ok':True,'version':'2.1.0','data_mode':'sample' if os.getenv('AGENTOPS_SEED_SAMPLE','0')=='1' else 'imported_or_empty','engine_mode':'deterministic_rules','external_side_effects':False,'authentication_enabled':bool(os.environ.get('AGENTOPS_API_TOKEN'))}

@app.get('/api/overview')
def overview():return store.get_overview()

@app.get('/api/workflows')
def workflows():return engine.all_workflows()

@app.post('/api/workflows/{slug}/run')
def execute(slug:str,force:bool=False):
    try:return engine.execute(slug,force=force)
    except ValueError as e:raise HTTPException(status_code=404,detail=str(e))

@app.post('/api/workflows/run-all')
def run_all(force:bool=False):
    return {'results':[engine.execute(slug,force=force) for slug in ('voc','ads','kol','brief')]}

@app.get('/api/runs')
def runs(limit:int=25):return store.get_runs(limit)

@app.get('/api/approvals')
def approvals():return store.get_approvals()

@app.post('/api/approvals/{item_id}/decision')
def decide(item_id:int,decision:ApprovalDecision):
    try:
        row=store.set_approval(item_id,decision.decision,decision.comment)
    except ValueError as e:raise HTTPException(status_code=409,detail=str(e))
    if row is None:raise HTTPException(status_code=404,detail='Approval not found')
    return row

@app.get('/api/approval-events')
def approval_events(limit:int=100):
    return store.get_approval_events(limit)

@app.get('/api/datasets/{dataset}')
def dataset(dataset:str):
    try:return store.table_rows(dataset)
    except ValueError as e:raise HTTPException(status_code=404,detail=str(e))

@app.post('/api/datasets/{dataset}/import')
async def import_dataset(dataset:str,file:UploadFile=File(...)):
    try:
        raw=await file.read(1024*1024+1)
        return store.import_csv(dataset,raw)
    except ValueError as e:
        raise HTTPException(status_code=422,detail=str(e))

@app.post('/api/datasets/{dataset}/ingest')
def ingest_json(dataset:str,records:list[dict]=Body(...)):
    try: return store.upsert_records(dataset,records)
    except ValueError as e: raise HTTPException(status_code=422,detail=str(e))

@app.get('/api/datasets/{dataset}/export')
def export_dataset(dataset:str):
    try: content=store.export_csv(dataset)
    except ValueError as e:raise HTTPException(status_code=404,detail=str(e))
    return PlainTextResponse(content,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename={dataset}.csv'})

@app.post('/api/reset')
def reset():
    ai_workflows.clear_reports()
    store.reset()
    return {'ok':True,'message':'已清空本地数据、AI分析记录、运行日志和审批记录；若显式开启样例模式则恢复样例'}

@app.get('/api/knowledge')
def knowledge(q:str=''):
    with store.connect() as db:
        if q:
            search='%'+q[:100].replace('%','').replace('_','')+'%'
            rows=db.execute('SELECT * FROM knowledge WHERE title LIKE ? OR body LIKE ? OR section LIKE ? LIMIT 20',(search,search,search)).fetchall()
        else:
            rows=db.execute('SELECT * FROM knowledge ORDER BY id').fetchall()
    return store.dicts(rows)

@app.get('/api/model-config')
def model_config():
    s=llm.settings()
    return {'configured':s['configured'],'model':s['model'],'fast_model':s['fast_model'],'mode':'dual_model_api'}

@app.get('/api/model-settings')
def get_model_settings():
    return model_settings.public()


@app.post('/api/model-settings')
def save_model_settings(item: ModelSettingsInput):
    try:
        return model_settings.save(item.api_key, item.base_url, item.model, item.fast_model)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError:
        raise HTTPException(status_code=500, detail='密钥保存失败，请检查本机用户权限')


@app.delete('/api/model-settings')
def delete_model_settings():
    return model_settings.clear()


@app.post('/api/model-settings/test')
def check_model_settings():
    try:
        return llm.test_connection('complex')
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post('/api/model-settings/test-all')
def check_all_model_settings():
    return llm.test_all_connections()


@app.get('/api/ai-reports')
def ai_reports(limit: int = 30):
    return ai_workflows.list_reports(limit)


@app.post('/api/workflows/{slug}/ai-analyze')
def ai_analyze_workflow(slug: str, item: AIWorkflowRequest):
    if not item.consent_to_external_processing:
        raise HTTPException(status_code=400, detail='请确认将脱敏后的工作流摘要发送到百炼进行AI分析。')
    try:
        return ai_workflows.analyze(slug, force=item.force, route=item.route)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post('/api/copilot')
def copilot(item:ChatRequest):
    """Rule-based explainable answer, not a language-model inference."""
    q=item.question.lower()
    over=store.get_overview()
    if item.mode=='llm':
        if not llm.settings()['configured']:
            raise HTTPException(status_code=409,detail='真实模型尚未配置；请打开「模型设置」粘贴API Key。')
        with store.connect() as db:
            voc,_,_=engine._voc(db)
            ads,_,_=engine._ads(db)
            kol,_,_=engine._kol(db)
            knowledge=store.dicts(db.execute('SELECT id,title,body FROM knowledge').fetchall())
        context={'overview':over,'voc_clusters':voc['clusters'],'ads':ads['details'],'kol':kol['scored'],'sop':knowledge,'sample_data':over['sample_data']}
        try:
            meta=llm.complete_with_meta(item.question,context,route=item.route)
        except RuntimeError as exc:
            raise HTTPException(status_code=502,detail=str(exc))
        return {'answer':meta['answer'],'model':meta['model'],'route':meta['route'],'usage':meta['usage'],'evidence':[{'id':k['id'],'title':k['title']} for k in knowledge], 'mode':'llm_api','disclaimer':'若启用了真实模型，数据将发送到所配置的第三方服务。输出需要人工核对。'}
    with store.connect() as db:
        matches=store.dicts(db.execute('SELECT id,title,section,body FROM knowledge').fetchall())
    if any(t in q for t in ('广告','投流','roas','预算','campaign','ad ')):
        with store.connect() as db:result,_,_=engine._ads(db)
        low=[x for x in result['details'] if x['roas']<1.8]
        answer=f'当前广告归因ROAS {result["roas"]:.2f}，花费 ${result["spend"]:,.0f}。其中 {len(low)} 条广告低于1.8：'+ ('、'.join(x['id']+' '+x['name'] for x in low) if low else '无')+'。建议先核对归因，再发起预算审批；系统不会自动更改账户预算。'
        tags=['analytics','ads']
    elif any(t in q for t in ('达人','kol','网红','creator')):
        with store.connect() as db:result,_,_=engine._kol(db)
        answer=f'已评估 {result["creator_count"]} 位达人候选，{result["shortlist"]} 位可进入A类评审。优先查看：'+ '、'.join(x['handle'] for x in result['scored'][:3])+'。报价和真实性应人工核验；不会自动外联。'
        tags=['kol']
    elif any(t in q for t in ('反馈','客诉','评论','用户','故障','customer','voc')):
        with store.connect() as db:result,_,_=engine._voc(db)
        key=result['clusters'][0] if result['clusters'] else None
        answer=f'共 {result["count"]} 条反馈记录，其中 {result["negative"]} 条低评分。首要风险主题：{key["topic"] if key else "暂无"}，关联 {key["count"] if key else 0} 条。需要产品与客服核查，不能把关键词分类当作确定的产品缺陷。'
        tags=['support']
    elif any(t in q for t in ('ceo','汇报','决策','日报','优先级')):
        with store.connect() as db:result,_,_=engine._brief(db)
        answer='CEO优先事项：'+'；'.join(x['title']+'（'+x['why']+'）' for x in result['issues'])+'。指标来自当前数据库；请核对数据范围、归因和真实性。'
        tags=['analytics','safety']
    else:
        answer=f'当前演示库含 {over["feedback_count"]} 条反馈、{over["creator_count"]} 位达人、投放总ROAS {over["roas"]:.2f}。你可以问我“哪些客诉最紧急”“哪些广告该调预算”“优先联系哪些KOL”“生成CEO简报”。回答基于本地规则与数据库，不是在线大模型生成。'
        tags=['brand','safety']
    evidence=[{'id':k['id'],'title':k['title']} for k in matches if k['section'] in tags][:3]
    return {'answer':answer,'evidence':evidence,'mode':'offline_rules','disclaimer':'规则辅助分析，不代表已验证的因果效果或自动执行。'}

@app.get('/api/brief.md')
def brief_download():
    with store.connect() as db:result,_,_=engine._brief(db)
    lines=['# CEO Daily Brief｜AgentOps Studio','', '> 数据可能来自用户导入或明确启用的虚构样例；生成内容是决策草案。','',
           f'- 总评论：{result["feedback_total"]}',f'- 低评分反馈：{result["negative_feedback"]}', f'- ROAS：{result["roas"]}',f'- 优先达人：{result["shortlist"]}', '', '## 建议行动']
    for x in result['issues']:
        lines.extend(['',f'### [{x["priority"]}] {x["title"]}',f'- 依据：{x["why"]}',f'- 原始记录：{", ".join(x["evidence"])}',f'- 责任人：{x["owner"]}',f'- 建议：{x["action"]}'])
    lines.extend(['','## 推断边界',result['caveat'],'','生成机制：本地规则聚合；未执行外部广告、KOL联系或客服操作。'])
    return PlainTextResponse('\n'.join(lines),media_type='text/markdown; charset=utf-8',headers={'Content-Disposition':'attachment; filename=agentops-executive-brief.md'})

app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')

@app.get('/')
def home():return FileResponse(ROOT/'web'/'index.html')
