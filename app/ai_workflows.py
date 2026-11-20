"""LLM-assisted workflow analysis with explicit consent and evidence-only context."""
from __future__ import annotations

import json
from . import engine, llm, store


def initialize() -> None:
    with store.connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS ai_workflow_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                workflow TEXT NOT NULL,
                route TEXT NOT NULL,
                model TEXT NOT NULL,
                answer TEXT NOT NULL,
                usage_json TEXT NOT NULL DEFAULT '{}',
                evidence_ids_json TEXT NOT NULL DEFAULT '[]',
                input_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_ai_reports_created ON ai_workflow_reports(created_at DESC)")


def _pick(row: dict, keys: tuple[str, ...]) -> dict:
    return {key: row.get(key) for key in keys if key in row}


def compact_context(workflow: str, result: dict) -> tuple[dict, list[str]]:
    """Keep only aggregates, decision metrics and evidence IDs; never send raw VOC comments."""
    evidence: list[str] = []
    if workflow == "voc":
        clusters = result.get("clusters", [])[:12]
        for item in clusters:
            evidence.extend(str(x) for x in item.get("sample_ids", []))
        context = {
            "workflow": "VOC",
            "feedback_count": result.get("count", 0),
            "negative_feedback_count": result.get("negative", 0),
            "clusters": [
                _pick(x, ("topic", "count", "negative_count", "risk_score", "rating", "sample_ids", "priority"))
                for x in clusters
            ],
            "rule": result.get("rule", ""),
            "privacy_note": "原始评论文本、客户姓名、联系方式均未发送；仅提供聚合指标和证据ID。",
        }
    elif workflow == "ads":
        details = result.get("details", [])[:15]
        evidence.extend(str(x.get("id")) for x in details if x.get("id") is not None)
        context = {
            "workflow": "ADS",
            "campaign_count": result.get("campaign_count", 0),
            "spend": result.get("spend", 0),
            "attributed_revenue": result.get("revenue", 0),
            "aggregate_roas": result.get("roas", 0),
            "campaigns": [
                _pick(x, ("id", "channel", "name", "market", "spend", "revenue", "roas", "ctr", "cvr", "cpa", "action"))
                for x in details
            ],
            "rule": result.get("rule", ""),
            "interpretation_boundary": "ROAS is attribution-based and is not causal incremental ROAS.",
        }
    elif workflow == "kol":
        scored = result.get("scored", [])[:15]
        evidence.extend(str(x.get("id")) for x in scored if x.get("id") is not None)
        context = {
            "workflow": "KOL",
            "candidate_count": result.get("creator_count", 0),
            "shortlist_count": result.get("shortlist", 0),
            "candidates": [
                _pick(x, ("id", "handle", "channel", "market", "followers", "engagement", "brand_fit", "fee", "fraud_flag", "score", "tier", "risk"))
                for x in scored
            ],
            "rule": result.get("rule", ""),
            "interpretation_boundary": "Scores are rule-based screening signals, not verified sales or fraud predictions.",
        }
    elif workflow == "brief":
        issues = result.get("issues", [])[:12]
        for issue in issues:
            evidence.extend(str(x) for x in issue.get("evidence", []))
        context = {
            "workflow": "CEO_BRIEF",
            "feedback_total": result.get("feedback_total", 0),
            "negative_feedback": result.get("negative_feedback", 0),
            "spend": result.get("spend", 0),
            "attributed_revenue": result.get("revenue", 0),
            "roas": result.get("roas", 0),
            "creator_shortlist": result.get("shortlist", 0),
            "priority_issues": [
                _pick(x, ("priority", "title", "why", "evidence", "owner", "action"))
                for x in issues
            ],
            "caveat": result.get("caveat", ""),
        }
    else:
        raise ValueError("Unknown workflow")
    return context, sorted(set(evidence))


def analyze(workflow: str, *, force: bool = False, route: str = "auto") -> dict:
    initialize()
    if workflow not in ("voc", "ads", "kol", "brief"):
        raise ValueError("Unknown workflow")
    if not llm.settings()["configured"]:
        raise RuntimeError("请先在模型设置中保存并验证 API Key。")

    run = engine.execute(workflow, force=force)
    context, evidence_ids = compact_context(workflow, run["result"])
    selected_route = ("complex" if workflow == "brief" else "fast") if route == "auto" else route
    if selected_route not in ("fast", "complex"):
        raise ValueError("route must be auto, fast or complex")

    question = (
        f"请分析 AgentOps Studio 的 {workflow.upper()} 工作流结果。"
        "请用中文输出一份可供业务负责人审阅的分析，必须包含："
        "一、数据事实；二、核心判断；三、风险与替代解释；"
        "四、按优先级排序的下一步建议；五、必须由人工审批的事项。"
        "不得重新计算或篡改输入指标，不得编造数据；每个关键判断尽量引用记录ID。"
        "如果证据不足，明确说明不足。涉及广告预算、客户沟通、达人合作时只能提出草案，不得声称已执行。"
    )
    meta = llm.complete_with_meta(question, context, route=selected_route)

    with store.connect() as db:
        cur = db.execute(
            """INSERT INTO ai_workflow_reports
               (run_id,workflow,route,model,answer,usage_json,evidence_ids_json,input_hash,created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                run["run_id"], workflow, selected_route, meta["model"], meta["answer"],
                json.dumps(meta.get("usage", {}), ensure_ascii=False),
                json.dumps(evidence_ids, ensure_ascii=False),
                run.get("input_hash", ""), store.utc_now(),
            ),
        )
        report_id = cur.lastrowid

    return {
        "report_id": report_id,
        "run_id": run["run_id"],
        "workflow": workflow,
        "run_status": run["status"],
        "route": selected_route,
        "model": meta["model"],
        "answer": meta["answer"],
        "usage": meta.get("usage", {}),
        "evidence_ids": evidence_ids,
        "privacy": "仅发送聚合指标、有限业务字段与证据ID；VOC原始评论文本未发送。",
        "created_at": store.utc_now(),
    }


def list_reports(limit: int = 30) -> list[dict]:
    initialize()
    with store.connect() as db:
        rows = db.execute(
            "SELECT * FROM ai_workflow_reports ORDER BY id DESC LIMIT ?",
            (min(max(1, limit), 100),),
        ).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        item["usage"] = json.loads(item.pop("usage_json") or "{}")
        item["evidence_ids"] = json.loads(item.pop("evidence_ids_json") or "[]")
        item["privacy"] = "仅发送聚合指标、有限业务字段与证据ID；VOC原始评论文本未发送。"
        output.append(item)
    return output


def clear_reports() -> None:
    initialize()
    with store.connect() as db:
        db.execute("DELETE FROM ai_workflow_reports")
