import re
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from agents.jd_agent import normalize_text
from agents.jd_agent.agent import score_job
from agents.core.schemas import ScoredJob
from agents.jd_agent.sites import DEFAULT_SOURCES, SITES
from backend.app.auth import get_current_user, get_owned
from backend.app.db import engine, get_session
from backend.app.models import Job, User
from backend.app.services.jobs import (
    get_push_setting, goal_from_setting, job_dict, load_profile, push_for_user, save_jobs, today_local,
)
from backend.app.services.agent_runtime import agent_ctx
from backend.app.services.tasks import submit
from agents.jd_agent.brief import build_brief
from backend.app.workflows.artifacts import save_artifact
from backend.app.workflows.engine import execute_step, start

router = APIRouter(prefix="/api", tags=["jobs"])


class ImportItem(BaseModel):
    text: str = Field(min_length=20, max_length=20000)
    url: str = ""


class ImportBody(BaseModel):
    """单条：text + url；批量：items（最多 10 条，来自批量粘贴或一键收藏书签）。"""
    text: str = Field(default="", max_length=20000)
    url: str = ""
    items: list[ImportItem] = Field(default_factory=list, max_length=10)


class TargetBody(BaseModel):
    value: bool = True


JOB_STATUSES = {"saved", "applied", "written_test", "interview", "hr_interview", "offer", "rejected", "dropped"}


class JobUpdate(BaseModel):
    status: str | None = None
    notes: str | None = Field(default=None, max_length=5000)


class PushBody(BaseModel):
    """求职偏好 + 每日推送。薪资为月薪 K，0 表示不限。"""
    enabled: bool = False
    titles: list[str] = Field(default_factory=list, max_length=3)
    cities: list[str] = Field(default_factory=list, max_length=5)
    sources: list[str] = Field(default_factory=lambda: DEFAULT_SOURCES[:], max_length=7)
    salary_min: int = Field(default=0, ge=0, le=200)
    salary_max: int = Field(default=0, ge=0, le=200)
    top_n: int = Field(default=10, ge=1, le=30)
    push_time: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


@router.post("/jobs/import")
def import_job(body: ImportBody, background: BackgroundTasks, user: User = Depends(get_current_user),
               session: Session = Depends(get_session)):
    user_id = user.id
    items = list(body.items)
    if body.text.strip():
        items.insert(0, ImportItem(text=body.text, url=body.url))
    if not items:
        raise HTTPException(400, "请粘贴岗位描述（至少 20 个字）")
    items = items[:10]
    goal = goal_from_setting(get_push_setting(session, user_id))

    def clean_url(u: str) -> str:
        u = u.strip()
        return u if re.match(r"^https?://", u) else ""

    def work(report):
        with Session(engine) as s:
            profile = load_profile(s, user_id)
        ids, new_ids, failed = [], [], []
        for n, item in enumerate(items, start=1):
            report(int(90 * (n - 1) / len(items)) + 5, f"解析第 {n}/{len(items)} 个岗位")
            try:
                with Session(engine) as s:
                    raw_hash = hashlib.sha256(item.text.strip().encode()).hexdigest()
                    cached = s.exec(select(Job).where(Job.user_id == user_id,
                                                      Job.raw_sha256 == raw_hash)).first()
                    run = start(s, user_id, "job_import", {"job_id": 0, "source_text": item.text,
                                                            "source_url": clean_url(item.url)})
                    def produce():
                        if cached:
                            parsed = ScoredJob.model_validate(cached.data)
                            parsed.source_url = clean_url(item.url) or parsed.source_url
                            score_job(parsed, profile, goal)
                        else:
                            parsed = normalize_text(item.text, url=clean_url(item.url), profile=profile, goal=goal,
                                                    ctx=agent_ctx(user_id, "jd"))
                        if not parsed.published_text:
                            parsed.published_text = "用户导入"
                        saved, created = save_jobs(s, user_id, [parsed])
                        job_id = saved[0]
                        row = s.get(Job, job_id)
                        unchanged = row.raw_sha256 == raw_hash and bool(row.brief_artifact_id)
                        row.raw_sha256 = raw_hash
                        run.subject = {"job_id": job_id}
                        if unchanged:
                            s.add(row)
                            s.add(run)
                            s.commit()
                            return {"job_id": job_id, "created": bool(created)}, "岗位内容未变，复用 JobBrief", \
                                [{"id": row.brief_artifact_id}]
                        brief = build_brief(parsed, item.text)
                        artifact = save_artifact(s, user_id, "JobBrief", {"job_id": row.id}, brief,
                                                 {"agent": "jd", "spec_id": "jd.normalize", "workflow_id": run.id},
                                                 sources=[{"kind": "job_page", "url": row.source_url}])
                        row.brief_artifact_id = artifact.id
                        s.add(row)
                        s.add(run)
                        s.commit()
                        return {"job_id": job_id, "created": bool(created)}, \
                            f"JobBrief v{artifact.version}，{len(brief['requirements'])} 条要求", \
                            [{"id": artifact.id, "version": artifact.version, "content_hash": artifact.content_hash}]
                    outcome = execute_step(s, run, "JD 已解析", produce,
                                           f"岗位原文 {len(item.text)} 字", node_type="agent")
                    ids.append(outcome["job_id"])
                    if outcome["created"]:
                        new_ids.append(outcome["job_id"])
            except Exception as exc:  # noqa: BLE001  单条失败不影响其它条
                failed.append(f"第 {n} 条：{str(exc)[:80]}")
                continue
        if not ids:
            raise ValueError("全部解析失败：" + "；".join(failed))
        return {"job_ids": ids, "new": len(new_ids), "failed": failed}

    return {"task_id": submit(background, session, user_id, "jobs:import", work).id}


@router.get("/jobs")
def list_jobs(scope: str = "all", status: str | None = None, user: User = Depends(get_current_user),
              session: Session = Depends(get_session)):
    query = select(Job).where(Job.user_id == user.id)
    if scope == "today":
        query = query.where(Job.pushed_date == today_local())
    elif scope == "target":
        query = query.where(Job.is_target == True)  # noqa: E712
    if status:
        if status not in JOB_STATUSES:
            raise HTTPException(400, "无效的投递状态")
        query = query.where(Job.status == status)
    rows = session.exec(query.order_by(Job.created_at.desc(), Job.score.desc()).limit(200)).all()
    if scope == "today":
        rows = sorted(rows, key=lambda j: j.score, reverse=True)
    return [job_dict(j) for j in rows]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return job_dict(get_owned(session, Job, job_id, user))


@router.patch("/jobs/{job_id}")
def update_job(job_id: int, body: JobUpdate, user: User = Depends(get_current_user),
               session: Session = Depends(get_session)):
    job = get_owned(session, Job, job_id, user)
    if body.status is not None:
        if body.status not in JOB_STATUSES:
            raise HTTPException(400, "无效的投递状态")
        if body.status != job.status:
            job.status_history = [*(job.status_history or []), {
                "status": body.status, "at": datetime.now(timezone.utc).isoformat(), "note": ""
            }]
            job.status = body.status
    if body.notes is not None:
        job.notes = body.notes
    job.updated_at = datetime.now(timezone.utc)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job_dict(job)


@router.post("/jobs/{job_id}/target")
def set_target(job_id: int, body: TargetBody, user: User = Depends(get_current_user),
               session: Session = Depends(get_session)):
    job = get_owned(session, Job, job_id, user)
    job.is_target = body.value
    session.add(job)
    session.commit()
    return job_dict(job)


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    session.delete(get_owned(session, Job, job_id, user))
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------- daily push

def _push_dict(s) -> dict:
    return {"enabled": s.enabled, "titles": s.titles, "cities": s.cities,
            "sources": s.sources or DEFAULT_SOURCES,
            "salary_min": s.salary_min or 0, "salary_max": s.salary_max or 0, "top_n": s.top_n or 10,
            "push_time": s.push_time,
            "last_push_date": s.last_push_date.isoformat() if s.last_push_date else None}


@router.get("/preferences")
@router.get("/push-setting")
def get_push(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return _push_dict(get_push_setting(session, user.id))


@router.put("/preferences")
@router.put("/push-setting")
def put_push(body: PushBody, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    s = get_push_setting(session, user.id)
    if body.salary_min and body.salary_max and body.salary_min > body.salary_max:
        raise HTTPException(400, "期望薪资下限不能高于上限")
    titles = [t.strip() for t in body.titles if t.strip()]
    if body.enabled and not titles:
        raise HTTPException(400, "开启每日推送前请填写目标岗位")
    s.enabled, s.push_time, s.top_n = body.enabled, body.push_time, body.top_n
    s.titles = titles
    s.cities = [c.strip() for c in body.cities if c.strip()]
    if any(source not in SITES for source in body.sources):
        raise HTTPException(400, "无效的市场样本来源")
    s.sources = list(dict.fromkeys(body.sources))
    s.salary_min, s.salary_max = body.salary_min, body.salary_max
    session.add(s)
    session.commit()
    session.refresh(s)
    return _push_dict(s)


@router.post("/push-setting/run-now")
def run_push_now(background: BackgroundTasks, user: User = Depends(get_current_user),
                 session: Session = Depends(get_session)):
    user_id = user.id
    return {"task_id": submit(background, session, user_id, "jobs:push",
                              lambda report: push_for_user(user_id, report)).id}
