"""User-facing memory management: view / confirm / edit / forget long-term preferences,
inspect or clear a working-memory session, and list recent agent runs (audit).

Fixed paths (/working, /runs) are declared before /{item_id} so they are matched first.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from backend.app.auth import get_current_user
from backend.app.db import get_session
from backend.app.models import User, WorkflowRun, WorkflowStep
from backend.app.services.agent_runtime import memory

router = APIRouter(prefix="/api/memory", tags=["memory"])

NAMESPACE_LABELS = {"global": "通用", "resume": "简历写作", "jd": "求职", "interview": "面试", "parser": "简历解析"}
USER_EDITABLE = ("global", "resume", "jd")        # 面试命名空间只由面试流程使用


class AddBody(BaseModel):
    namespace: str = "resume"
    value: str = Field(min_length=2, max_length=200)


class EditBody(BaseModel):
    value: str = Field(min_length=2, max_length=200)


def _uid(user: User) -> str:
    return str(user.id)


def _item(i) -> dict:
    return {**i.as_dict(), "namespace_label": NAMESPACE_LABELS.get(i.namespace, i.namespace)}


# ---------------------------------------------------------------- working memory & runs
@router.get("/working")
def working_memory(agent: str, session: str, user: User = Depends(get_current_user)):
    view = memory().working.view(_uid(user), agent, session, keep_recent=20)
    return {"summary": view.summary,
            "turns": [{"role": t.role, "content": t.content, "created_at": t.created_at} for t in view.turns]}


@router.delete("/working")
def clear_working_memory(agent: str, session: str, user: User = Depends(get_current_user)):
    memory().working.clear(_uid(user), agent, session)
    return {"ok": True}


@router.get("/runs")
def agent_runs(limit: int = 30, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    runs = memory().store.list_runs(_uid(user), limit=min(max(limit, 1), 100))
    workflows = session.exec(select(WorkflowRun).where(WorkflowRun.user_id == user.id)).all()
    by_run = {row.id: row for row in workflows}
    steps = session.exec(select(WorkflowStep).where(WorkflowStep.run_id.in_(list(by_run)))).all() if by_run else []
    by_step = {row.id: by_run[row.run_id] for row in steps}
    keep = ("run_id", "agent", "spec_id", "status", "model", "iterations", "repairs", "tool_calls",
            "visible_tools", "memory", "usage", "error", "started_at", "duration_ms", "skills", "workflow_step_id")
    return [{k: r.get(k) for k in keep} | {"context_tokens": (r.get("manifest") or {}).get("total_tokens"),
            "workflow_id": by_step[r["workflow_step_id"]].id if r.get("workflow_step_id") in by_step else "",
            "workflow_kind": by_step[r["workflow_step_id"]].kind if r.get("workflow_step_id") in by_step else ""}
            for r in runs]


# ---------------------------------------------------------------- long-term preferences
@router.get("")
def list_memory(user: User = Depends(get_current_user)):
    items = memory().preferences.list(_uid(user), statuses=("active", "proposed"))
    return {"items": [_item(i) for i in items],
            "namespaces": [{"value": n, "label": NAMESPACE_LABELS[n]} for n in USER_EDITABLE]}


@router.post("")
def add_memory(body: AddBody, user: User = Depends(get_current_user)):
    if body.namespace not in USER_EDITABLE:
        raise HTTPException(400, "无效的记忆分类")
    item = memory().preferences.propose(_uid(user), body.namespace, body.value, explicit=True, source="user_manual")
    if item is None:
        raise HTTPException(400, "内容太短")
    return _item(item)


@router.post("/{item_id}/confirm")
def confirm_memory(item_id: int, user: User = Depends(get_current_user)):
    item = memory().preferences.confirm(_uid(user), item_id, source="confirmed_proposal")
    if item is None:
        raise HTTPException(404, "记忆不存在")
    return _item(item)


@router.patch("/{item_id}")
def edit_memory(item_id: int, body: EditBody, user: User = Depends(get_current_user)):
    item = memory().preferences.edit(_uid(user), item_id, body.value)
    if item is None:
        raise HTTPException(404, "记忆不存在")
    return _item(item)


@router.delete("/{item_id}")
def forget_memory(item_id: int, user: User = Depends(get_current_user)):
    if not memory().preferences.forget(_uid(user), item_id):
        raise HTTPException(404, "记忆不存在")
    return {"ok": True}
