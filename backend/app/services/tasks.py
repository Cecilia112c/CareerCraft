"""Background agent tasks: task row + progress + result, polled by the frontend.

Task functions receive only a `report(progress, stage)` callback and must open
their own DB sessions (the request session is closed after the response).
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable

from fastapi import BackgroundTasks
from sqlmodel import Session

from backend.app.db import engine
from backend.app.models import Task

log = logging.getLogger("careercraft.tasks")
Report = Callable[[int, str], None]
_lock = threading.Lock()
_heavy_slots = threading.BoundedSemaphore(2)


def _update(task_id: str, **fields) -> None:
    with _lock, Session(engine) as session:
        task = session.get(Task, task_id)
        if task is None:
            return
        for key, value in fields.items():
            setattr(task, key, value)
        task.updated_at = datetime.now(timezone.utc)
        session.add(task)
        session.commit()


def make_reporter(task_id: str) -> Report:
    def report(progress: int, stage: str) -> None:
        _update(task_id, progress=max(0, min(int(progress), 99)), stage=stage[:200])
    return report


def run_task(task_id: str, fn: Callable[[Report], dict | None]) -> None:
    _update(task_id, status="pending", stage="等待执行")
    try:
        with _heavy_slots:
            _update(task_id, status="running", stage="开始")
            result = fn(make_reporter(task_id)) or {}
        _update(task_id, status="done", progress=100, stage="完成", result=result)
    except Exception as exc:  # noqa: BLE001
        log.exception("task %s failed", task_id)
        _update(task_id, status="failed", error=str(exc)[:500] or exc.__class__.__name__)


def submit(background: BackgroundTasks, session: Session, user_id: int, kind: str,
           fn: Callable[[Report], dict | None]) -> Task:
    task = Task(id=uuid.uuid4().hex, user_id=user_id, kind=kind)
    session.add(task)
    session.commit()
    session.refresh(task)
    background.add_task(run_task, task.id, fn)
    return task
