"""Results & reports API endpoints."""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app import repositories as repo
from app.__init_db import get_db
from app.auth.deps import get_current_user, get_current_space
from app.models.user import User
from app.models import Agent, Dataset, Rule, AIJudgeModel, Annotation
from app.models.test_case import TestCase

router = APIRouter(prefix="/tasks", tags=["Results"])


def _fmt(v, decimals: int = 2) -> str:
    """Format a number to fixed decimals, or '-' if None."""
    if v is None:
        return "-"
    return f"{v:.{decimals}f}"


@router.get("/{task_id}/results")
async def list_results(task_id: str, passed: bool | None = None,
                       page: int = 1, size: int = 50,
                       db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user),
                       current_space: str | None = Depends(get_current_space)):
    results, total = await repo.list_task_results(db, task_id, space_id=current_space, passed=passed, page=page, size=size)

    # Enrich with expected_output from test cases
    task = await repo.get_task(db, task_id)
    expected_map: dict[str, str] = {}
    if task and task.dataset_ids:
        stmt = select(TestCase.case_id, TestCase.expected_output).where(
            TestCase.dataset_id.in_(task.dataset_ids))
        rows = (await db.execute(stmt)).all()
        expected_map = {row.case_id: row.expected_output for row in rows if row.expected_output}

    items = []
    for r in results:
        d = {
            "id": r.id, "task_id": r.task_id, "agent_id": r.agent_id,
            "case_id": r.case_id,
            "raw_input": r.raw_input,
            "raw_output": r.raw_output,
            "expected_output": expected_map.get(r.case_id, ""),
            "response_time_ms": r.response_time_ms,
            "status_code": r.status_code,
            "error": r.error,
            "passed": r.passed,
            "total_score": r.total_score,
            "scores": r.scores,
            "executed_at": str(r.executed_at) if r.executed_at else None,
        }
        items.append(d)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{task_id}/results/{result_id}")
async def get_result(task_id: str, result_id: str, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user),
                      current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.Task, task_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    result = await repo.get_task_result(db, result_id)
    if not result or result.task_id != task_id:
        raise HTTPException(404, "Result not found")
    return result


@router.get("/{task_id}/summary")
async def task_summary(task_id: str, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user),
                       current_space: str | None = Depends(get_current_space)):
    task = await repo.get_task(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if not await repo.verify_space_access(db, repo.Task, task_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    summary = await repo.get_task_summary(db, task_id)
    return {"task_id": task_id, "task_name": task.name, **summary}


# ── Helper: resolve names from IDs ──────────────────────────────

async def _resolve_names(db: AsyncSession, task) -> dict:
    """Resolve agent, dataset, rule, and AI judge IDs to names."""
    info: dict = {}

    # Agents
    agent_ids = task.agent_ids or []
    if agent_ids:
        stmt = select(Agent.id, Agent.name).where(Agent.id.in_(agent_ids))
        rows = (await db.execute(stmt)).all()
        info["agents"] = {row.id: row.name for row in rows}
    else:
        info["agents"] = {}

    # Datasets
    dataset_ids = task.dataset_ids or []
    if dataset_ids:
        stmt = select(Dataset.id, Dataset.name).where(Dataset.id.in_(dataset_ids))
        rows = (await db.execute(stmt)).all()
        info["datasets"] = {row.id: row.name for row in rows}
    else:
        info["datasets"] = {}

    # Rules
    rule_ids = (task.config or {}).get("rule_ids") or []
    if rule_ids:
        stmt = select(Rule.id, Rule.name, Rule.type).where(Rule.id.in_(rule_ids))
        rows = (await db.execute(stmt)).all()
        info["rules"] = {row.id: {"name": row.name, "type": row.type} for row in rows}
    else:
        info["rules"] = {}

    # AI judges
    ai_config = task.ai_scoring_config or []
    if ai_config and isinstance(ai_config, list) and len(ai_config) > 0:
        judge_ids = ai_config if isinstance(ai_config, list) else []
        stmt = select(AIJudgeModel.id, AIJudgeModel.name, AIJudgeModel.model_name).where(AIJudgeModel.id.in_(judge_ids))
        rows = (await db.execute(stmt)).all()
        info["ai_judges"] = {row.id: {"name": row.name, "model": row.model_name} for row in rows}
    else:
        info["ai_judges"] = {}

    return info


async def _get_last_annotations(db: AsyncSession, result_ids: list[str]) -> dict[str, dict]:
    """Return the last annotation per task_result_id."""
    if not result_ids:
        return {}
    stmt = (
        select(Annotation)
        .where(Annotation.task_result_id.in_(result_ids))
        .order_by(Annotation.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    last: dict[str, dict] = {}
    for ann in rows:
        if ann.task_result_id not in last:
            last[ann.task_result_id] = {
                "score": ann.score,
                "comment": ann.comment,
                "label": ann.label,
                "annotator": ann.annotator,
                "status": ann.status,
                "created_at": str(ann.created_at) if ann.created_at else None,
            }
    return last


async def _get_expected_map(db: AsyncSession, dataset_ids: list[str]) -> dict[str, str]:
    """Build case_id → expected_output mapping."""
    if not dataset_ids:
        return {}
    stmt = select(TestCase.case_id, TestCase.expected_output).where(
        TestCase.dataset_id.in_(dataset_ids),
        TestCase.expected_output.isnot(None),
    )
    rows = (await db.execute(stmt)).all()
    return {row.case_id: row.expected_output for row in rows}


# ── Export endpoint ──────────────────────────────────────────────

@router.get("/{task_id}/report")
async def export_report(task_id: str, format: str = "json", db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user),
                       current_space: str | None = Depends(get_current_space)):
    """Export task results with full detail in various formats."""
    task = await repo.get_task(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if not await repo.verify_space_access(db, repo.Task, task_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")

    summary = await repo.get_task_summary(db, task_id)
    results, _ = await repo.list_task_results(db, task_id, page=1, size=10_000)

    # Resolve names
    names = await _resolve_names(db, task)

    # Expected output map
    expected_map = await _get_expected_map(db, task.dataset_ids or [])

    # Last annotation per result
    result_ids = [r.id for r in results]
    last_annotations = await _get_last_annotations(db, result_ids)

    # ── Build enriched results ──
    enriched = []
    for r in results:
        ann = last_annotations.get(r.id)
        entry = {
            "case_id": r.case_id,
            "agent_id": r.agent_id,
            "agent_name": names["agents"].get(r.agent_id, r.agent_id),
            "passed": r.passed,
            "score": r.total_score,
            "response_time_ms": r.response_time_ms,
            "status_code": r.status_code,
            "error": r.error or "",
            "raw_input": r.raw_input,
            "raw_output": r.raw_output,
            "expected_output": expected_map.get(r.case_id, ""),
            "scores": r.scores,
            "annotation_score": ann["score"] if ann else "",
            "annotation_label": ann["label"] if ann else "",
            "annotation_comment": ann["comment"] if ann else "",
            "annotation_annotator": ann["annotator"] if ann else "",
            "annotation_status": ann["status"] if ann else "",
            "annotation_date": ann["created_at"] if ann else "",
        }
        enriched.append(entry)

    # Task config metadata
    cfg = task.config or {}
    rule_ids = cfg.get("rule_ids") or []
    rule_names = [names["rules"].get(rid, {}).get("name", rid) for rid in rule_ids]
    ai_config = task.ai_scoring_config or []
    judge_names = []
    if isinstance(ai_config, list):
        judge_names = [names["ai_judges"].get(jid, {}).get("name", jid) for jid in ai_config]
    agent_names = [names["agents"].get(aid, aid) for aid in (task.agent_ids or [])]
    dataset_names = [names["datasets"].get(did, did) for did in (task.dataset_ids or [])]

    # ── Helpers for tabular formats ──
    def _fmt_score(v, decimals: int = 2) -> str:
        if v is None:
            return "-"
        return f"{v:.{decimals}f}"

    def _rules_text(scores) -> str:
        """规则评分明细 → text."""
        if not scores or not scores.get("rules"):
            return ""
        parts = []
        for rule in scores["rules"]:
            parts.append(f"{rule.get('name', rule.get('rule_type', '?'))}: {_fmt_score(rule.get('score'))} ({'PASS' if rule.get('passed') else 'FAIL'})")
        return "; ".join(parts)

    def _objectives_text(scores) -> str:
        """评估维度明细 → text."""
        if not scores or not scores.get("objectives"):
            return ""
        parts = []
        for name, data in (scores.get("objectives") or {}).items():
            parts.append(f"{name}: {_fmt_score(data.get('score'))} wt={data.get('weight','-')} th={data.get('threshold',0.7)} ({'PASS' if data.get('passed') else 'FAIL'})")
        return "; ".join(parts)

    def _rules_html(scores) -> str:
        if not scores or not scores.get("rules"):
            return ""
        rows = ""
        for rule in scores["rules"]:
            cls = "pass" if rule.get("passed") else "fail"
            rows += f"<tr><td style='padding:2px 8px'>{rule.get('name', rule.get('rule_type', '?'))}</td><td style='padding:2px 8px'>{_fmt_score(rule.get('score'))}</td><td style='padding:2px 8px' class='{cls}'>{'PASS' if rule.get('passed') else 'FAIL'}</td></tr>"
        return f'<table style="font-size:12px;border-collapse:collapse"><tr><th style="padding:2px 8px">规则</th><th style="padding:2px 8px">得分</th><th style="padding:2px 8px">结果</th></tr>{rows}</table>'

    def _objectives_html(scores) -> str:
        if not scores or not scores.get("objectives"):
            return ""
        rows = ""
        for name, data in (scores.get("objectives") or {}).items():
            cls = "pass" if data.get("passed") else "fail"
            rows += f"<tr><td style='padding:2px 8px'>{name}</td><td style='padding:2px 8px'>{_fmt_score(data.get('score'))}</td><td style='padding:2px 8px'>wt={data.get('weight','-')}</td><td style='padding:2px 8px'>th={data.get('threshold',0.7)}</td><td style='padding:2px 8px' class='{cls}'>{'PASS' if data.get('passed') else 'FAIL'}</td></tr>"
        return f'<table style="font-size:12px;border-collapse:collapse"><tr><th style="padding:2px 8px">维度</th><th style="padding:2px 8px">得分</th><th style="padding:2px 8px">权重</th><th style="padding:2px 8px">阈值</th><th style="padding:2px 8px">结果</th></tr>{rows}</table>'

    # ── JSON ──
    if format == "json":
        return {
            "task_name": task.name,
            "task_id": task_id,
            "status": task.status,
            "created_at": str(task.created_at),
            "agents": agent_names,
            "datasets": dataset_names,
            "rules": rule_names,
            "ai_judges": judge_names,
            "config": {
                "concurrency": cfg.get("concurrency"),
                "timeout_ms": cfg.get("timeout_ms"),
                "global_threshold": cfg.get("global_threshold", 0.7),
            },
            "summary": summary,
            "results": enriched,
        }
    # ── CSV ──
    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "case_id", "agent", "passed", "score", "response_ms", "status_code", "error",
            "规则评分明细",
            "评估维度明细",
            "annotation_score", "annotation_label", "annotation_comment",
        ])
        for e in enriched:
            writer.writerow([
                e["case_id"], e["agent_name"], e["passed"], _fmt(e["score"]),
                e["response_time_ms"], e["status_code"], e["error"],
                _rules_text(e["scores"]),
                _objectives_text(e["scores"]),
                e["annotation_score"], e["annotation_label"], e["annotation_comment"],
            ])
        return PlainTextResponse(output.getvalue(), media_type="text/csv")

    # ── Markdown ──
    if format == "md":
        header = f"# Report: {task.name}"
        meta = f"""**Status:** {task.status}  |  **Created:** {str(task.created_at)[:19]}
**Agents:** {', '.join(agent_names) or '-'}
**Datasets:** {', '.join(dataset_names) or '-'}
**Rules:** {', '.join(rule_names) or '-'}
**AI Judges:** {', '.join(judge_names) or '-'}
**Concurrency:** {cfg.get('concurrency', '-')}  |  **Timeout:** {cfg.get('timeout_ms', '-')}ms  |  **Threshold:** {cfg.get('global_threshold', 0.7)}
"""
        summary_table = f"""## Summary

| Metric | Value |
|--------|-------:|
| Total | {summary['total']} |
| Passed | {summary['passed']} |
| Failed | {summary['failed']} |
| Pass Rate | {summary['pass_rate']*100:.1f}% |
| Avg Score | {_fmt(summary['avg_score'])} |
"""
        results_table = """## Results

| Case ID | Agent | Passed | Score | Response(ms) | Error | 规则评分明细 | 评估维度明细 | 审核评分 | 审核标签 |
|---------|-------|--------|-------|-------------|-------|-------------|-------------|---------|---------|
"""
        rows = []
        for e in enriched:
            rows.append(
                f"| {e['case_id']} | {e['agent_name']} | {'✅' if e['passed'] else '❌'} "
                f"| {_fmt(e['score'])} | {e['response_time_ms'] or '-'} | {e['error'] or ''} "
                f"| {_rules_text(e['scores']) or '-'} | {_objectives_text(e['scores']) or '-'} "
                f"| {e['annotation_score'] or ''} | {e['annotation_label'] or ''} |"
            )
        lines = [header, "", meta, summary_table, results_table]
        lines.extend(rows)
        return PlainTextResponse("\n".join(lines), media_type="text/markdown")

    # ── HTML ──
    if format == "html":
        def _escape(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        rows_html = ""
        for e in enriched:
            passed_cls = "pass" if e["passed"] else "fail"
            rules_sub = _rules_html(e["scores"])
            obj_sub = _objectives_html(e["scores"])
            rows_html += (
                f"<tr>"
                f"<td>{_escape(e['case_id'])}</td>"
                f"<td>{_escape(e['agent_name'])}</td>"
                f"<td class='{passed_cls}'>{'PASS' if e['passed'] else 'FAIL'}</td>"
                f"<td>{_fmt(e['score'])}</td>"
                f"<td>{e['response_time_ms'] or '-'}</td>"
                f"<td>{_escape(e['error'])}</td>"
                f"<td style='font-size:12px'>{rules_sub}</td>"
                f"<td style='font-size:12px'>{obj_sub}</td>"
                f"<td>{e['annotation_score'] or ''}</td>"
                f"<td>{_escape(e['annotation_label'] or '')}</td>"
                f"<td>{_escape(e['annotation_comment'] or '')}</td>"
                f"</tr>"
            )

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Report: {_escape(task.name)}</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 1200px; margin: 2em auto; font-size: 14px; }}
h1 {{ margin-bottom: 4px; }}
.meta {{ color: #555; font-size: 13px; margin-bottom: 1.5em; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
th {{ background: #f5f5f5; white-space: nowrap; }}
.summary-cards {{ display: flex; gap: 1em; margin: 1em 0; }}
.summary-cards > div {{ padding: 1em; flex: 1; border-radius: 6px; text-align: center; }}
.pass {{ color: #3f8600; }} .fail {{ color: #cf1322; }}
</style></head><body>
<h1>Report: {_escape(task.name)}</h1>
<div class="meta">
<strong>Status:</strong> {_escape(task.status)} | <strong>Created:</strong> {str(task.created_at)[:19]}<br>
<strong>Agents:</strong> {_escape(', '.join(agent_names)) or '-'}<br>
<strong>Datasets:</strong> {_escape(', '.join(dataset_names)) or '-'}<br>
<strong>Rules:</strong> {_escape(', '.join(rule_names)) or '-'}<br>
<strong>AI Judges:</strong> {_escape(', '.join(judge_names)) or '-'}<br>
<strong>Concurrency:</strong> {cfg.get('concurrency', '-')} | <strong>Timeout:</strong> {cfg.get('timeout_ms', '-')}ms | <strong>Threshold:</strong> {cfg.get('global_threshold', 0.7)}
</div>
<div class="summary-cards">
<div style="background:#e8f5e9;"><strong>Passed</strong><br>{summary['passed']}/{summary['total']}</div>
<div style="background:#ffebee;"><strong>Failed</strong><br>{summary['failed']}/{summary['total']}</div>
<div style="background:#e3f2fd;"><strong>Avg Score</strong><br>{_fmt(summary['avg_score'])}</div>
<div style="background:#fff3e0;"><strong>Pass Rate</strong><br>{summary['pass_rate']*100:.1f}%</div>
</div>
<h2>Results</h2>
<table><thead><tr>
<th>Case ID</th><th>Agent</th><th>Passed</th><th>Score</th><th>Response(ms)</th><th>Error</th><th>规则评分明细</th><th>评估维度明细</th><th>审核评分</th><th>审核标签</th><th>审核评语</th>
</tr></thead><tbody>
{rows_html}
</tbody></table></body></html>"""
        return PlainTextResponse(html, media_type="text/html")

    raise HTTPException(400, f"Unsupported format: {format}")
