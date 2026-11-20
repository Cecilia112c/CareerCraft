"""Job persistence and daily push (in-app only)."""

from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from agents.core.schemas import ProfileData, ScoredJob
from agents.jd_agent import JobGoal, is_fresh, score_job, search_jobs
from backend.app.config import TIMEZONE
from backend.app.db import engine
from backend.app.models import Job, Profile, PushSetting
from backend.app.services.tasks import Report

log = logging.getLogger("careercraft.jobs")


def today_local() -> date:
    return datetime.now(ZoneInfo(TIMEZONE)).date()


def load_profile(session: Session, user_id: int) -> ProfileData:
    row = session.exec(select(Profile).where(Profile.user_id == user_id)).first()
    return ProfileData.model_validate(row.data if row else {})


def job_dict(job: Job) -> dict:
    data = job.data or {}
    return {
        "id": job.id, "title": job.title, "company": job.company, "city": job.city,
        "salary": job.salary, "published_text": job.published_text,
        "published_at": job.published_at.isoformat() if job.published_at else None,
        "score": job.score, "is_target": job.is_target, "source_url": job.source_url,
        "pushed_date": job.pushed_date.isoformat() if job.pushed_date else None,
        "created_at": job.created_at.isoformat(), "detail": data,
        "pref_match": data.get("pref_match", True), "pref_notes": data.get("pref_notes", []),
        "site": job.site, "origin": job.origin, "detail_level": job.detail_level,
        "status": job.status, "status_history": job.status_history or [],
        "notes": job.notes, "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def job_posting(job: Job) -> ScoredJob:
    return ScoredJob.model_validate(job.data or {"title": job.title})


def save_jobs(session: Session, user_id: int, jobs: list[ScoredJob],
              pushed: bool = False) -> tuple[list[int], list[int]]:
    """Upsert by source_url. Returns (all ids, newly created ids)."""
    all_ids, new_ids = [], []
    for item in jobs:
        row = None
        if item.source_url:
            row = session.exec(select(Job).where(Job.user_id == user_id,
                                                 Job.source_url == item.source_url)).first()
        is_new = row is None
        if is_new:
            row = Job(user_id=user_id, source_url=item.source_url)
        row.title, row.company, row.city = item.title, item.company, item.city
        row.salary, row.published_text = item.salary, item.published_text
        row.published_at, row.score = item.published_at, item.score
        row.data = item.model_dump(mode="json")
        if is_new and pushed:
            row.pushed_date = today_local()
        session.add(row)
        session.commit()
        session.refresh(row)
        all_ids.append(row.id)
        if is_new:
            new_ids.append(row.id)
    return all_ids, new_ids


def get_push_setting(session: Session, user_id: int) -> PushSetting:
    setting = session.get(PushSetting, user_id)
    if setting is None:
        setting = PushSetting(user_id=user_id)
        session.add(setting)
        session.commit()
        session.refresh(setting)
    return setting


def goal_from_setting(setting: PushSetting) -> JobGoal:
    return JobGoal(titles=setting.titles or [], cities=setting.cities or [],
                   salary_min=setting.salary_min or 0, salary_max=setting.salary_max or 0)


def push_for_user(user_id: int, report: Report) -> dict:
    """Daily refresh: re-sample the market skill demand for the target titles (no job postings pushed,
    no LLM calls). The job library itself only contains jobs the user collected."""
    from backend.app.services.insights import market_insight

    with Session(engine) as session:
        setting = get_push_setting(session, user_id)
        titles, cities = list(setting.titles or []), list(setting.cities or [])
    if not titles:
        raise ValueError("请先在“求职偏好”中填写目标岗位")
    data = market_insight(user_id, titles, cities, report)
    with Session(engine) as session:
        setting = get_push_setting(session, user_id)
        setting.last_push_date = today_local()
        session.add(setting)
        session.commit()
    return {"new": len(data.get("terms", [])), "sample_size": data.get("sample_size", 0),
            "coverage": data.get("coverage", 0), "missing_top": data.get("missing_top", []),
            "warnings": data.get("warnings", [])}


def push_tick() -> None:
    """Called by the scheduler: push for every user whose push time has come today."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    today, hhmm = now.date(), now.strftime("%H:%M")
    with Session(engine) as session:
        due = session.exec(select(PushSetting).where(PushSetting.enabled == True)).all()  # noqa: E712
        claimed: list[tuple[int, date | None]] = []
        for s in due:   # 每天一次：到了设定时间、今天还没推送过
            if s.titles and s.push_time <= hhmm and s.last_push_date != today:
                claimed.append((s.user_id, s.last_push_date))
                s.last_push_date = today            # 先占位，防止重复推送
                session.add(s)
        session.commit()
    for user_id, previous in claimed:
        try:
            result = push_for_user(user_id, lambda p, s: None)
            log.info("daily push user=%s new=%s", user_id, result["new"])
        except Exception:  # noqa: BLE001
            log.exception("daily push failed for user %s", user_id)
            with Session(engine) as session:
                s = session.get(PushSetting, user_id)
                if s:
                    s.last_push_date = previous     # 失败则下个周期重试
                    session.add(s)
                    session.commit()
