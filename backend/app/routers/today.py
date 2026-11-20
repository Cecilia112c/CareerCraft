"""Live dashboard summary from saved jobs."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from backend.app.auth import get_current_user
from backend.app.db import get_session
from backend.app.models import Job, Todo, User
from backend.app.services.insights import library_insight

router = APIRouter(prefix="/api", tags=["today"])


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@router.get("/today")
def today(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    now = datetime.now(timezone.utc)
    jobs = session.exec(select(Job).where(Job.user_id == user.id)).all()
    reminders = []
    funnel = {s: 0 for s in ("saved", "applied", "written_test", "interview", "hr_interview", "offer", "rejected", "dropped")}
    for job in jobs:
        funnel[job.status] = funnel.get(job.status, 0) + 1
        age = now - utc(job.updated_at or job.created_at)
        if job.status == "saved" and age > timedelta(days=3):
            reminders.append({"job_id": job.id, "title": job.title, "reason": "收藏超过 3 天，尚未投递"})
        elif job.status == "applied" and age > timedelta(days=14):
            reminders.append({"job_id": job.id, "title": job.title, "reason": "投递超过 14 天，尚无进展"})
    insight = library_insight(session, user.id)
    return {"reminders": reminders,
            "funnel": funnel, "insight": insight}


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    kind: str
    due_at: datetime
    job_id: int | None = None


@router.get("/todos")
def list_todos(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return session.exec(select(Todo).where(Todo.user_id == user.id).order_by(Todo.done, Todo.due_at)).all()


@router.post("/todos")
def create_todo(body: TodoCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if body.kind not in ("interview", "written_test", "other"):
        raise HTTPException(422, "无效的待办类型")
    if body.job_id and not session.exec(select(Job.id).where(Job.id == body.job_id, Job.user_id == user.id)).first():
        raise HTTPException(404, "职位不存在")
    todo = Todo(user_id=user.id, **body.model_dump())
    session.add(todo)
    session.commit()
    session.refresh(todo)
    return todo


@router.patch("/todos/{todo_id}")
def update_todo(todo_id: int, done: bool, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    todo = session.exec(select(Todo).where(Todo.id == todo_id, Todo.user_id == user.id)).first()
    if not todo:
        raise HTTPException(404, "待办不存在")
    todo.done = done
    session.add(todo)
    session.commit()
    return todo


@router.delete("/todos/{todo_id}")
def delete_todo(todo_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    todo = session.exec(select(Todo).where(Todo.id == todo_id, Todo.user_id == user.id)).first()
    if not todo:
        raise HTTPException(404, "待办不存在")
    session.delete(todo)
    session.commit()
    return {"ok": True}
