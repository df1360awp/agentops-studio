"""Explainable, deterministic Agent-style workflows with human approval gates."""
from __future__ import annotations
import json
import time
import math
from collections import defaultdict
from . import store
from .store import connect, dicts, utc_now

FLOW_DEFS=[
 {'id':'voc','no':'01','name':'Voice of Customer','cn':'用户反馈智能分流','domain':'DTC / 客诉','icon':'message','description':'跨渠道评论归一化 → 问题聚类 → 风险分级 → 工单草稿','steps':['数据采集','主题识别','问题聚类','优先级评估','人工复核']},
 {'id':'ads','no':'02','name':'Performance Intelligence','cn':'投流预算优化','domain':'广告 / ROI','icon':'chart','description':'归因指标计算 → 低效识别 → 预算建议 → 人工审批','steps':['指标读取','ROAS / CPA','阈值判定','预算草案','人工审批']},
 {'id':'kol','no':'03','name':'Creator Intelligence','cn':'KOL 合作筛选','domain':'达人 / 品牌','icon':'users','description':'达人评分 → 风险过滤 → 分级排序 → 合作邀约草稿','steps':['达人数据','匹配度评分','异常识别','邀约草案','人工审批']},
 {'id':'brief','no':'04','name':'Executive Daily Brief','cn':'CEO 决策简报','domain':'决策 / 汇报','icon':'file','description':'整合反馈、投放、达人数据 → 提炼风险与行动优先级','steps':['拉取业务数据','聚合结论','证据核对','优先事项','生成简报']},
]

KEYWORDS={
 '数据丢失 / 导出异常':['lost','disappear','crash','froze','export','save','file','录音丢失','导出失败'],
 '蓝牙连接 / 新手设置':['bluetooth','pairing','connect','onboarding','setup','guide','连接','配对'],
 '物流与附件':['shipping','delayed','tracking','package','usb cable','物流','快递'],
 '价格与订阅':['pricing','subscription','expensive','价格','订阅'],
 '积极反馈':['great','love','perfect','amazing','excellent','满意','喜欢'],
}
WEIGHT={'数据丢失 / 导出异常':5,'蓝牙连接 / 新手设置':4,'物流与附件':3,'价格与订阅':2,'积极反馈':0,'其他':1}


def safe_ratio(a,b):return round(a/b,3) if b else 0


def categorize(comment):
    l=comment.lower()
    scores={name:sum(1 for word in words if word in l) for name,words in KEYWORDS.items()}
    if max(scores.values(),default=0)==0:return '其他'
    # For negative reviews positive keywords should not win over functional complaints.
    return max(scores,key=lambda k:(scores[k],WEIGHT[k]))


def _step(i,label,detail):
    return {'index':i,'label':label,'detail':detail,'status':'success'}


def _voc(db):
    data=dicts(db.execute('SELECT * FROM feedback ORDER BY created_at DESC').fetchall())
    classified=[]
    groups=defaultdict(list)
    for row in data:
        topic=categorize(row['comment'])
        item={**row,'topic':topic,'risk':round((6-row['rating'])*WEIGHT[topic]*3.2)}
        classified.append(item)
        groups[topic].append(item)
    clusters=[]
    for topic,rows in groups.items():
        negative=sum(x['rating']<=2 for x in rows)
        score=min(100,round(WEIGHT[topic]*10 + negative*8 +len(rows)*3))
        clusters.append({'topic':topic,'count':len(rows),'negative_count':negative,'risk_score':score,'rating':round(sum(x['rating'] for x in rows)/len(rows),1), 'sample_ids':[x['id'] for x in rows[:4]],'priority':'P0' if score>=70 else 'P1' if score>=50 else 'P2' if score>=30 else 'P3'})
    clusters.sort(key=lambda x:-x['risk_score'])
    top=clusters[0] if clusters else None
    approvals=[]
    if top and top['risk_score']>=50:
        approvals.append({'kind':'support','title':f'{top["priority"]} · {top["topic"]}','detail':f'{top["count"]} 条反馈，{top["negative_count"]} 条差评；记录依据：{", ".join(top["sample_ids"])}。需核实问题根因，不将关键词分类当作已确认缺陷。', 'recommended_action':'提交产品/客服联合复核；批准后仅生成待处理任务，不自动向客户发送消息。'})
    return {'count':len(data),'negative':sum(x['rating']<=2 for x in data),'clusters':clusters, 'sample':classified[:12], 'key_issue':top['topic'] if top else '无', 'rule':'风险分=主题权重×10 + 差评数×8 + 总提及数×3（上限100）'}, [
     _step(1,'数据采集',f'读取 {len(data)} 条 DTC 反馈'),_step(2,'主题识别','离线词典与评级规则分类，每条保留原始文本'),_step(3,'问题聚类',f'归纳 {len(clusters)} 个主题'),_step(4,'优先级评估',f'首要风险：{top["topic"] if top else "暂无"}'),_step(5,'人工复核',f'{len(approvals)} 项需要人工确认')], approvals


def _ads(db):
    rows=dicts(db.execute('SELECT * FROM campaigns ORDER BY id').fetchall())
    detail=[]; approvals=[]
    for x in rows:
        roas=safe_ratio(x['revenue'],x['spend']); ctr=safe_ratio(x['clicks'],x['impressions'])*100
        cvr=safe_ratio(x['conversions'],x['clicks'])*100
        cpa=safe_ratio(x['spend'],x['conversions'])
        if x['spend']>=500 and roas<1.8:
            action='建议减少预算 15%'; delta=-.15
        elif x['conversions']>=20 and roas>3.2:
            action='建议测试性增加预算 10%'; delta=.1
        else:
            action='保持预算并继续观察'; delta=0
        item={**x,'roas':round(roas,2),'ctr':round(ctr,2),'cvr':round(cvr,2),'cpa':round(cpa,2),'action':action,'delta':delta,'budget_change':round(x['spend']*delta,0)}
        detail.append(item)
        if delta:
            approvals.append({'kind':'ads','title':f'{x["channel"]} · {x["name"]}', 'detail':f'花费 ${x["spend"]:,.0f}；归因营收 ${x["revenue"]:,.0f}；ROAS {roas:.2f}；CPA ${cpa:.2f}。仅为基于当前导入的归因数据的规则建议。','recommended_action':f'{action}（试算变动 ${x["spend"]*delta:+,.0f}）；审批后也不会调用广告平台执行。'})
    spend=sum(x['spend'] for x in rows);revenue=sum(x['revenue'] for x in rows)
    return {'campaign_count':len(rows),'spend':spend,'revenue':revenue,'roas':round(revenue/spend,2) if spend else 0,'details':detail,'recommended_changes':len(approvals), 'rule':'ROAS<1.8→减15%；ROAS>3.2且转化≥20→增10%；所有建议人工审核'},[
        _step(1,'指标读取',f'{len(rows)} 条投放计划'),_step(2,'ROAS / CPA','按归因营收、成本与转化统一计算'),_step(3,'阈值判定','使用公开规则，避免黑盒自动调价'),_step(4,'预算草案',f'{len(approvals)} 条拟调整建议'),_step(5,'人工审批','无对外广告账号操作')], approvals


def _kol(db):
    rows=dicts(db.execute('SELECT * FROM creators').fetchall())
    scored=[];approvals=[]
    for x in rows:
        engagement_part=min(100,max(0,x['engagement']*12))
        price_part=max(0,100-x['fee']/100)
        score=round(.55*x['brand_fit']+.3*engagement_part+.15*price_part-(35 if x['fraud_flag'] else 0))
        item={**x,'score':max(0,min(100,score)),'tier':'A' if score>=80 else 'B' if score>=68 else 'C','risk':'需人工排查' if x['fraud_flag'] else '未标记'}
        scored.append(item)
    scored.sort(key=lambda x:-x['score'])
    for x in scored:
        if x['score']>=80 and not x['fraud_flag']:
            approvals.append({'kind':'kol','title':f'达人邀约 · {x["handle"]}', 'detail':f'{x["channel"]} / {x["market"]} · 品牌匹配度 {x["brand_fit"]}/100 · 互动率 {x["engagement"]}% · 报价 ${x["fee"]:,.0f} · 规则评分 {x["score"]}/100。', 'recommended_action':f'生成合作邀约草稿；由品牌负责人审核后手动发送给 {x["handle"]}。不得自动签约付款。'})
    return {'creator_count':len(rows),'shortlist':len(approvals),'scored':scored,'rule':'评分 = 55%品牌匹配 + 30%互动 + 15%报价适配 − 异常惩罚；仅用于候选优先级'},[
       _step(1,'达人数据',f'导入 {len(rows)} 条达人候选'),_step(2,'匹配度评分','结合相关度、互动率与报价'),_step(3,'异常识别','流量异常标记扣分，不能代替真实性审计'),_step(4,'邀约草案',f'筛选 {len(approvals)} 位 A 级候选'),_step(5,'人工审批','不自动发送、签约或付款')],approvals


def _brief(db):
    f,fs,fa=_voc(db)
    a,aa,ab=_ads(db)
    k,ks,ka=_kol(db)
    top=f['clusters'][0] if f['clusters'] else None
    issues=[
      {'priority':'P0','title':'优先排查用户体验风险','why':f'{top["topic"] if top else "暂无"} · {top["count"] if top else 0} 条涉及反馈', 'evidence':top['sample_ids'] if top else [], 'owner':'产品 + 客服', 'action':'核查复现步骤并确认是否需要补丁公告'},
      {'priority':'P1','title':'复核低效投放组合','why':f'{len([x for x in a["details"] if x["roas"]<1.8])} 条投放 ROAS 低于规则阈值', 'evidence':[x['id'] for x in a['details'] if x['roas']<1.8], 'owner':'增长运营', 'action':'人工确认归因与预算调节建议'},
      {'priority':'P1','title':'启动优质达人合作评审','why':f'{k["shortlist"]} 位 A 级达人候选', 'evidence':[x['id'] for x in k['scored'] if x['score']>=80 and not x['fraud_flag']], 'owner':'品牌 / KOL', 'action':'核查真实性并审阅合作报价与邀约内容'}
    ]
    result={'title':'CEO EXECUTIVE BRIEF','feedback_total':f['count'],'negative_feedback':f['negative'],'roas':a['roas'],'spend':a['spend'],'revenue':a['revenue'],'shortlist':k['shortlist'],'issues':issues,'caveat':'数据来自用户导入或显式开启的虚构样例。预算结果是归因指标，不证明因果增量；建议均需人工确认。'}
    steps=[_step(1,'拉取业务数据','DTC评论、广告投放与达人数据'),_step(2,'聚合结论','统一关键指标口径'),_step(3,'证据核对','每条行动附原始记录ID'),_step(4,'优先事项','按用户风险、预算、品牌合作分层'),_step(5,'生成简报','仅生成内部草案，无对外自动执行')]
    return result,steps,[]

ENGINES={'voc':_voc,'ads':_ads,'kol':_kol,'brief':_brief}


def execute(slug, *, force=False):
    if slug not in ENGINES:
        raise ValueError('Unknown workflow')
    start=time.perf_counter()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")  # Serialize hash lookup and write to prevent concurrent duplicate approvals.
        snapshot=store.input_fingerprint(db,slug)
        if not force:
            old=db.execute("SELECT * FROM runs WHERE workflow=? AND input_hash=? AND status='completed' ORDER BY id DESC LIMIT 1",(slug,snapshot)).fetchone()
            if old is not None:
                return {'run_id':old['id'],'workflow':slug,'status':'cached',
                        'steps':json.loads(old['steps_json']),'result':json.loads(old['result_json']),
                        'approvals_created':0,'mode':'offline_rules','input_hash':snapshot}
        result,steps,approvals=ENGINES[slug](db)
        elapsed_ms=round((time.perf_counter()-start)*1000,2)
        result['_telemetry']={'engine_ms':elapsed_ms,'measurement_scope':'Python rule processing + read; excludes browser rendering','metric_type':'technical_latency_not_business_roi'}
        cur=db.execute('INSERT INTO runs(workflow,started_at,status,steps_json,result_json,mode,input_hash) VALUES (?,?,?,?,?,?,?)', (slug,utc_now(),'completed',json.dumps(steps,ensure_ascii=False),json.dumps(result,ensure_ascii=False),'offline_rules',snapshot))
        run_id=cur.lastrowid
        for a in approvals:
            db.execute('INSERT INTO approvals(run_id,kind,title,detail,recommended_action,status,created_at) VALUES(?,?,?,?,?,?,?)',(run_id,a['kind'],a['title'],a['detail'],a['recommended_action'],'pending',utc_now()))
        return {'run_id':run_id,'workflow':slug,'status':'completed','steps':steps,'result':result,'approvals_created':len(approvals),'mode':'offline_rules','engine_ms':elapsed_ms,'input_hash':snapshot}


def all_workflows():return FLOW_DEFS
