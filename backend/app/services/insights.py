"""Skill-demand insights for the jobs page and the daily refresh (no LLM calls)."""

from __future__ import annotations

import logging

from sqlmodel import Session, select

from agents.core.schemas import full_text
from agents.jd_agent.agent import candidate_skills
from agents.jd_agent.insight import aggregate, extract_terms, job_text
from agents.jd_agent.search_api import search_domain
from agents.jd_agent.sites import DEFAULT_SOURCES, SITES
from backend.app.db import engine
from backend.app.models import InsightSnapshot, Job
from backend.app.services.jobs import get_push_setting, load_profile
from backend.app.services.tasks import Report

log = logging.getLogger("careercraft.insights")
MAX_QUERIES = 8


def my_terms(session: Session, user_id: int) -> set[str]:
    profile = load_profile(session, user_id)
    return extract_terms(full_text(profile), candidate_skills(profile))


def library_insight(session: Session, user_id: int, status: str | None = None) -> dict:
    query = select(Job).where(Job.user_id == user_id)
    if status:
        query = query.where(Job.status == status)
    jobs = session.exec(query).all()
    docs = [(j.id, extract_terms(job_text(j.data or {"title": j.title}), (j.data or {}).get("keywords") or []))
            for j in jobs]
    docs = [d for d in docs if d[1]]
    out = aggregate(docs, my_terms(session, user_id)).as_dict()
    out["source"] = "library"
    return out


def market_insight(user_id: int, titles: list[str], cities: list[str], report: Report) -> dict:
    """Search JD snippets for the target titles and count skill terms. Postings may be stale; only words count."""
    with Session(engine) as session:
        setting = get_push_setting(session, user_id)
        sources = [s for s in (setting.sources or DEFAULT_SOURCES) if s in SITES]
        mine = my_terms(session, user_id)
    city = cities[0] if cities else ""
    queries = [(SITES[s][0], f"{t} 岗位职责 任职要求 {city}".strip()) for t in titles[:2] for s in sources][:MAX_QUERIES]
    seen: dict[str, str] = {}
    warnings: list[str] = []
    for n, (domain, q) in enumerate(queries, start=1):
        report(5 + int(85 * (n - 1) / max(len(queries), 1)), f"采集市场样本 {n}/{len(queries)}")
        try:
            for hit in search_domain(q, domain, count=20):
                text = f"{hit.title}\n{hit.snippet}"
                if hit.url and len(text) > 40:
                    seen.setdefault(hit.url, text)
        except Exception as exc:  # noqa: BLE001  单个来源失败不影响其它来源
            msg = str(exc)[:150]
            if msg not in warnings:
                warnings.append(msg)
            if "Key" in msg or "余额" in msg or "未配置" in msg:
                break
    docs = [(url, extract_terms(text)) for url, text in seen.items()]
    docs = [d for d in docs if d[1]]
    if not docs:
        raise ValueError("没有采集到可用的岗位描述样本" + (f"：{warnings[0]}" if warnings else ""))
    data = aggregate(docs, mine).as_dict()
    for t in data["terms"]:
        t["doc_ids"] = []                      # 市场样本只看词频，不展示具体职位
    data.update(source="market", warnings=warnings, sample_size=len(docs))
    with Session(engine) as session:
        row = InsightSnapshot(user_id=user_id, kind="market",
                              query={"titles": titles, "cities": cities, "sources": sources}, data=data)
        session.add(row)
        session.commit()
        session.refresh(row)
        data["created_at"] = row.created_at.isoformat()
        data["query"] = row.query
    report(98, "完成")
    return data


def latest_market(session: Session, user_id: int) -> dict | None:
    row = session.exec(select(InsightSnapshot).where(InsightSnapshot.user_id == user_id,
                                                      InsightSnapshot.kind == "market")
                       .order_by(InsightSnapshot.id.desc())).first()
    if row is None:
        return None
    return {**row.data, "created_at": row.created_at.isoformat(), "query": row.query}
