"""The coordinator persists a gate and resumes without rerunning completed steps."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.models import WorkflowStep
from backend.app.workflows.engine import execute_step, recover_interrupted, resume_gate, start, wait_gate


def test_multi_step_gate_and_resume():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        run = start(session, 8, "resume_generate", {"resume_id": 3})
        execute_step(session, run, "匹配", lambda: ({}, "匹配完成", []), terminal=False)
        assert run.status == "running" and run.finished_at is None
        gate = wait_gate(session, run, "确认缺口", "缺少一条依据")
        assert gate.status == run.status == "waiting_user"
        resume_gate(session, run, "用户决定跳过")
        assert gate.status == "done" and run.status == "running"
        execute_step(session, run, "写作", lambda: ({}, "已生成", []))
        assert run.status == "done" and run.finished_at is not None


def test_abandoned_step_becomes_retryable():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        run = start(session, 8, "job_import", {"job_id": 3})
        step = WorkflowStep(id="step_old", run_id=run.id, name="解析", status="running",
                            started_at=datetime.now(timezone.utc) - timedelta(hours=1))
        session.add(step)
        session.commit()
        assert recover_interrupted(session) == 1
        session.refresh(step)
        session.refresh(run)
        assert step.status == "pending" and run.status == "failed"


def test_restart_recovers_workflow_before_first_step_started():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        run = start(session, 8, "job_import", {"job_id": 0, "source_text": "JD"})
        assert recover_interrupted(session, older_than_seconds=0) == 1
        session.refresh(run)
        step = session.exec(select(WorkflowStep).where(WorkflowStep.run_id == run.id)).one()
        assert run.status == "failed" and step.status == "pending" and step.error
