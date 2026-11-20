"""Save a user selected, single page clip after frontend parsing."""

from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from agents.core.schemas import ScoredJob
from agents.jd_agent import normalize_text, score_job
from agents.jd_agent.brief import build_brief
from backend.app.auth import get_current_user
from backend.app.db import get_session
from backend.app.models import Job, User
from backend.app.services.agent_runtime import agent_ctx
from backend.app.services.jobs import get_push_setting, goal_from_setting, job_posting, load_profile
from backend.app.workflows.artifacts import save_artifact
from backend.app.workflows.engine import execute_step, start

router = APIRouter(prefix="/api/clip", tags=["clip"])


class Card(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    salary: str = Field(default="", max_length=80)
    company: str = Field(default="", max_length=120)
    area: str = Field(default="", max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=20)
    url: str = Field(max_length=500)


class Detail(Card):
    skills: list[str] = Field(default_factory=list, max_length=30)
    description: str = Field(min_length=40, max_length=20000)
    responsibilities: list[str] = Field(default_factory=list, max_length=100)
    requirements: list[str] = Field(default_factory=list, max_length=100)


class ClipSave(BaseModel):
    detail: Detail | None = None
    cards: list[Card] = Field(default_factory=list, max_length=50)


def clean_url(raw: str) -> str:
    parts = urlsplit(raw)
    host = parts.hostname or ""
    allowed = any(host == domain or host.endswith("." + domain)
                  for domain in ("zhipin.com", "liepin.com", "shixiseng.com", "nowcoder.com"))
    if parts.scheme != "https" or not allowed or ("zhipin.com" in host and "/job_detail/" not in parts.path):
        raise HTTPException(400, "不是支持的职位详情链接")
    return urlunsplit(("https", parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


@router.post("/save")
def save_clip(body: ClipSave, user: User = Depends(get_current_user),
              session: Session = Depends(get_session)):
    if body.detail is None and not body.cards:
        raise HTTPException(400, "请选择职位详情或卡片")
    ids: list[int] = []
    if body.detail:
        d = body.detail
        url = clean_url(d.url)
        existing = session.exec(select(Job).where(Job.user_id == user.id, Job.source_url == url)).first()
        if not existing:
            profile = load_profile(session, user.id)
            goal = goal_from_setting(get_push_setting(session, user.id))
            if d.responsibilities or d.requirements:
                posting = ScoredJob(title=d.title, company=d.company, city=d.area, salary=d.salary,
                                    source_url=url, keywords=d.skills,
                                    responsibilities=d.responsibilities, requirements=d.requirements,
                                    summary=d.description[:500])
                posting = score_job(posting, profile, goal)
            else:
                posting = normalize_text(d.description, url=url, profile=profile, goal=goal,
                                         ctx=agent_ctx(user.id, "jd"))
            existing = Job(user_id=user.id, source_url=url, title=d.title, company=d.company,
                           city=d.area, salary=d.salary, score=posting.score,
                           data=posting.model_dump(mode="json"),
                           site="boss" if "zhipin.com" in url else "other",
                           origin="clip_detail", detail_level="full")
            session.add(existing)
            session.flush()
        elif existing.detail_level == "summary":
            existing.detail_level = "full"
            existing.origin = "clip_detail"
            existing.data = ScoredJob(title=d.title, company=d.company, city=d.area,
                                      salary=d.salary, source_url=url, keywords=d.skills,
                                      responsibilities=d.responsibilities,
                                      requirements=d.requirements,
                                      summary=d.description[:500]).model_dump(mode="json")
            existing.updated_at = datetime.now(timezone.utc)
            session.add(existing)
        ids.append(existing.id)
    card_ids: list[int] = []
    for card in body.cards:
        url = clean_url(card.url)
        if session.exec(select(Job.id).where(Job.user_id == user.id, Job.source_url == url)).first():
            continue
        posting = ScoredJob(title=card.title, company=card.company, city=card.area, salary=card.salary,
                            source_url=url, keywords=card.tags, summary=" · ".join(card.tags))
        row = Job(user_id=user.id, source_url=url, title=card.title, company=card.company,
                  city=card.area, salary=card.salary, data=posting.model_dump(mode="json"),
                  site="boss" if "zhipin.com" in url else "other", origin="clip_card", detail_level="summary")
        session.add(row)
        session.flush()
        card_ids.append(row.id)
    session.commit()
    if body.detail:
        for job_id in ids:
            row = session.get(Job, job_id)
            if row.brief_artifact_id:
                continue
            run = start(session, user.id, "job_import", {"job_id": row.id})
            def produce():
                brief = build_brief(job_posting(row), body.detail.description)
                artifact = save_artifact(session, user.id, "JobBrief", {"job_id": row.id}, brief,
                                         {"agent": "jd", "spec_id": "jd.brief", "workflow_id": run.id},
                                         sources=[{"kind": "job_page", "url": row.source_url}])
                row.brief_artifact_id = artifact.id
                session.add(row)
                session.commit()
                return artifact, f"JobBrief v{artifact.version}，{len(brief['requirements'])} 条要求", \
                    [{"id": artifact.id, "version": artifact.version}]
            execute_step(session, run, "JD 已解析", produce, f"职位详情 {len(body.detail.description)} 字",
                         node_type="agent")
    return {"job_ids": [*ids, *card_ids], "new": len(card_ids)}
