"""Persisted workflow timeline for deterministic, retryable steps."""

import uuid
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
from typing import Callable

from sqlmodel import Session, select

from backend.app.models import Task, WorkflowRun, WorkflowStep
from backend.app.workflows.definitions import DEFINITIONS

_current_step: ContextVar[str] = ContextVar("workflow_step_id", default="")


def current_step_id() -> str:
    return _current_step.get()


def start(session: Session, user_id: int, kind: str, subject: dict) -> WorkflowRun:
    run = WorkflowRun(id="wf_" + uuid.uuid4().hex, user_id=user_id, kind=kind, subject=subject)
    session.add(run)
    nodes = DEFINITIONS.get(kind, ())
    if kind == "resume_generate" and not subject.get("job_id"):
        nodes = nodes[-1:]
    for ordinal, node in enumerate(nodes):
        session.add(WorkflowStep(id="step_" + uuid.uuid4().hex, run_id=run.id,
                                 ordinal=ordinal, name=node.name, node_type=node.node_type))
    session.commit()
    session.refresh(run)
    return run


def execute_step(session: Session, run: WorkflowRun, name: str, fn: Callable[[], tuple[object, str, list[dict]]],
                 input_summary: str = "", input_refs: list[dict] | None = None,
                 terminal: bool = True, node_type: str = "code") -> object:
    step = session.exec(select(WorkflowStep).where(WorkflowStep.run_id == run.id,
                                                  WorkflowStep.name == name,
                                                  WorkflowStep.status == "pending")).first()
    if step is None:
        ordinal = len(session.exec(select(WorkflowStep).where(WorkflowStep.run_id == run.id)).all())
        step = WorkflowStep(id="step_" + uuid.uuid4().hex, run_id=run.id, ordinal=ordinal, name=name)
    step.status, step.node_type, step.error = "running", node_type, ""
    step.input_summary, step.input_refs = input_summary, input_refs or []
    step.started_at, step.finished_at = datetime.now(timezone.utc), None
    session.add(step)
    session.commit()
    token = _current_step.set(step.id)
    try:
        result, summary, refs = fn()
        step.status = "done"
        step.output_summary = summary
        step.output_refs = refs
        run.status = "done" if terminal else "running"
        return result
    except Exception as exc:
        step.status = "failed"
        step.error = str(exc)[:500]
        run.status = "failed"
        raise
    finally:
        _current_step.reset(token)
        try:
            from agents.harness import get_runtime
            runs = get_runtime().store.list_runs(str(run.user_id), limit=100)
            step.agent_run_ids = [item["run_id"] for item in runs if item.get("workflow_step_id") == step.id]
        except Exception:
            pass
        step.finished_at = datetime.now(timezone.utc)
        if run.status in {"done", "failed"}:
            run.finished_at = step.finished_at
        session.add(step)
        session.add(run)
        session.commit()


def wait_gate(session: Session, run: WorkflowRun, name: str, summary: str,
              input_refs: list[dict] | None = None) -> WorkflowStep:
    if run.status != "running":
        raise ValueError("只有运行中的工作流可以进入等待节点")
    step = session.exec(select(WorkflowStep).where(WorkflowStep.run_id == run.id,
                                                  WorkflowStep.name == name,
                                                  WorkflowStep.status == "pending")).first()
    if step is None:
        ordinal = len(session.exec(select(WorkflowStep).where(WorkflowStep.run_id == run.id)).all())
        step = WorkflowStep(id="step_" + uuid.uuid4().hex, run_id=run.id, ordinal=ordinal, name=name)
    step.node_type, step.status, step.input_summary = "gate", "waiting_user", summary
    step.input_refs, step.started_at = input_refs or [], datetime.now(timezone.utc)
    run.status = "waiting_user"
    session.add(step)
    session.add(run)
    session.commit()
    return step


def resume_gate(session: Session, run: WorkflowRun, summary: str) -> WorkflowStep:
    if run.status != "waiting_user":
        raise ValueError("工作流没有等待用户确认的节点")
    step = session.exec(select(WorkflowStep).where(
        WorkflowStep.run_id == run.id, WorkflowStep.node_type == "gate",
        WorkflowStep.status == "waiting_user")).first()
    if not step:
        raise ValueError("等待节点不存在")
    step.status, step.output_summary, step.finished_at = "done", summary, datetime.now(timezone.utc)
    run.status = "running"
    session.add(step)
    session.add(run)
    session.commit()
    return step


def skip_gate(session: Session, run: WorkflowRun, name: str, summary: str) -> None:
    step = session.exec(select(WorkflowStep).where(WorkflowStep.run_id == run.id,
                                                  WorkflowStep.name == name,
                                                  WorkflowStep.status == "pending")).first()
    if step:
        step.status, step.output_summary = "skipped", summary
        step.started_at = step.finished_at = datetime.now(timezone.utc)
        session.add(step)
        session.commit()


def recover_interrupted(session: Session, *, older_than_seconds: int = 600) -> int:
    """Reset abandoned running steps after process restart; caller can retry them."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
    steps = session.exec(select(WorkflowStep).where(
        WorkflowStep.status == "running")).all()
    recovered = 0
    for step in steps:
        started = step.started_at
        if not started or started.replace(tzinfo=timezone.utc) > cutoff:
            continue
        step.status, step.error = "pending", "执行中断，等待重试"
        run = session.get(WorkflowRun, step.run_id)
        if run:
            run.status, run.finished_at = "failed", datetime.now(timezone.utc)
            session.add(run)
        session.add(step)
        recovered += 1
    if older_than_seconds == 0:
        for run in session.exec(select(WorkflowRun).where(WorkflowRun.status == "running")).all():
            ordered = session.exec(select(WorkflowStep).where(WorkflowStep.run_id == run.id)
                                   .order_by(WorkflowStep.ordinal)).all()
            first = next((item for item in ordered if item.status not in {"done", "skipped"}), None)
            if first and first.status == "pending":
                first.error = "执行中断，等待重试"
                run.status, run.finished_at = "failed", datetime.now(timezone.utc)
                session.add(first)
                session.add(run)
                recovered += 1
    if older_than_seconds == 0:
        for task in session.exec(select(Task).where(Task.status.in_(["pending", "running"]))).all():
            task.status, task.error = "failed", "服务重启后任务中断，请在工作流中重试"
            task.updated_at = datetime.now(timezone.utc)
            session.add(task)
    session.commit()
    return recovered
