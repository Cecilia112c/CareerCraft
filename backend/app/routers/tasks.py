from fastapi import APIRouter, Depends
from sqlmodel import Session

from backend.app.auth import get_current_user, get_owned
from backend.app.db import get_session
from backend.app.models import Task, User

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task_id}")
def get_task(task_id: str, user: User = Depends(get_current_user),
             session: Session = Depends(get_session)):
    task = get_owned(session, Task, task_id, user)
    return {"id": task.id, "kind": task.kind, "status": task.status, "progress": task.progress,
            "stage": task.stage, "result": task.result, "error": task.error}
