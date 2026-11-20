"""Material parsing and failed workflow recovery stay behind the task boundary."""

import io
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.auth import get_current_user
from backend.app.db import get_session
from backend.app.main import app
from backend.app.models import Artifact, Interview, Job, KnowledgeChunk, KnowledgeSource, Profile, Resume, ResumeVersion, User, WorkflowStep
from backend.app.workflows.artifacts import save_artifact
from backend.app.workflows.engine import start


def _client(monkeypatch, tmp_path):
    db = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(db)
    with Session(db) as session:
        user = User(username="ingest", password_hash="x")
        session.add(user)
        session.commit()
        session.refresh(user)
    def sessions():
        with Session(db) as session:
            yield session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = sessions
    monkeypatch.setattr("backend.app.routers.knowledge.engine", db)
    monkeypatch.setattr("backend.app.services.tasks.engine", db)
    monkeypatch.setattr("backend.app.routers.knowledge.UPLOAD_DIR", tmp_path)
    return TestClient(app), db, user


def test_uploaded_document_is_parsed_by_task(monkeypatch, tmp_path, llm):
    client, db, _ = _client(monkeypatch, tmp_path)
    llm.push({"claims": []})
    try:
        response = client.post("/api/knowledge/sources", files={"file": ("sample.txt", "Python API service".encode())})
        assert response.status_code == 200, response.text
        task = client.get(f"/api/tasks/{response.json()['task_id']}").json()
        assert task["status"] == "done", task
        with Session(db) as session:
            source = session.exec(select(KnowledgeSource)).one()
            chunks = session.exec(select(KnowledgeChunk)).all()
            assert source.status == "ready" and chunks[0].text == "Python API service"
    finally:
        app.dependency_overrides.clear()


def test_unsafe_zip_fails_in_bounded_task(monkeypatch, tmp_path):
    client, db, _ = _client(monkeypatch, tmp_path)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../escape.txt", "unsafe")
    try:
        response = client.post("/api/knowledge/sources", files={"file": ("unsafe.zip", stream.getvalue())})
        assert response.status_code == 200, response.text
        task = client.get(f"/api/tasks/{response.json()['task_id']}").json()
        assert task["status"] == "failed"
        with Session(db) as session:
            source = session.exec(select(KnowledgeSource)).one()
            assert source.status == "failed"
            assert not session.exec(select(KnowledgeChunk)).all()
    finally:
        app.dependency_overrides.clear()


def test_retry_cannot_jump_over_failed_or_waiting_step(monkeypatch, tmp_path):
    client, db, user = _client(monkeypatch, tmp_path)
    try:
        with Session(db) as session:
            run = start(session, user.id, "resume_generate", {"resume_id": 9, "job_id": 3})
            steps = session.exec(select(WorkflowStep).where(WorkflowStep.run_id == run.id)
                                 .order_by(WorkflowStep.ordinal)).all()
            steps[0].status = "failed"
            run.status = "failed"
            session.add(steps[0])
            session.add(run)
            session.commit()
            run_id, later_id = run.id, steps[-1].id
        response = client.post(f"/api/workflows/{run_id}/steps/{later_id}/retry")
        assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_profile_update_proposal_requires_fresh_user_confirmation(monkeypatch, tmp_path):
    client, db, user = _client(monkeypatch, tmp_path)
    with Session(db) as session:
        session.add(Profile(user_id=user.id, data={"projects": [{"id": "p1", "name": "Search",
            "impact": [{"id": "b1", "text": "Improved search"}]}]}))
        resume = Resume(user_id=user.id, title="Search", current_version=1)
        session.add(resume)
        session.flush()
        session.add(ResumeVersion(resume_id=resume.id, version=1, data={"projects": [{"id": "p1",
            "name": "Search", "impact": [{"id": "b1", "text": "Improved search latency"}]}]}))
        session.commit()
        resume_id = resume.id
    try:
        proposed = client.post(f"/api/resumes/{resume_id}/sync-proposal", params={"version": 1})
        assert proposed.status_code == 200, proposed.text
        artifact = proposed.json()
        assert artifact["kind"] == "ProfileUpdateProposal"
        assert artifact["body"]["diffs"][0]["key"] == "b1"
        applied = client.post(f"/api/resumes/{resume_id}/sync", json={
            "version": 1, "keys": ["b1"], "proposal_id": artifact["id"]})
        assert applied.status_code == 200 and applied.json()["applied"] == 1
        replay = client.post(f"/api/resumes/{resume_id}/sync", json={
            "version": 1, "keys": ["b1"], "proposal_id": artifact["id"]})
        assert replay.status_code == 409
        with Session(db) as session:
            assert session.get(Artifact, artifact["id"]).status == "superseded"
            assert session.exec(select(Profile)).one().data["projects"][0]["impact"][0]["text"] == "Improved search latency"
    finally:
        app.dependency_overrides.clear()


def test_failed_jd_parse_can_retry_from_persisted_source(monkeypatch, tmp_path, llm):
    client, db, user = _client(monkeypatch, tmp_path)
    source = "招聘后端开发工程师，要求熟悉 Python 开发，负责接口设计与服务维护。"
    with Session(db) as session:
        session.add(Profile(user_id=user.id, data={}))
        run = start(session, user.id, "job_import", {"job_id": 0, "source_text": source, "source_url": ""})
        step = session.exec(select(WorkflowStep).where(WorkflowStep.run_id == run.id)).one()
        step.status = "failed"
        run.status = "failed"
        session.add(step)
        session.add(run)
        session.commit()
        run_id, step_id = run.id, step.id
    llm.push({"is_job_page": True, "title": "后端开发", "company": "示例公司",
              "requirements": ["熟悉 Python 开发"], "keywords": ["Python"]})
    try:
        response = client.post(f"/api/workflows/{run_id}/steps/{step_id}/retry")
        assert response.status_code == 200, response.text
        with Session(db) as session:
            assert session.exec(select(WorkflowStep)).one().status == "done"
            assert session.exec(select(Artifact).where(Artifact.kind == "JobBrief")).one()
    finally:
        app.dependency_overrides.clear()


def test_interrupted_match_resumes_on_same_workflow(monkeypatch, tmp_path):
    client, db, user = _client(monkeypatch, tmp_path)
    monkeypatch.setattr("backend.app.routers.workflows.engine", db)
    monkeypatch.setattr("backend.app.routers.resumes.engine", db)
    monkeypatch.setattr("backend.app.routers.resumes.match_with_agent", lambda *_args, **_kwargs: {
        "job_id": 1, "matches": [{"req_id": "r1", "requirement": "Kafka",
                                   "coverage": "none", "evidence": [], "reason": "没有依据"}],
        "missing_req_ids": ["r1"]})
    with Session(db) as session:
        session.add(Profile(user_id=user.id, data={}))
        job = Job(user_id=user.id, title="Backend", detail_level="full", data={"title": "Backend"})
        session.add(job)
        session.flush()
        brief = save_artifact(session, user.id, "JobBrief", {"job_id": job.id},
                              {"title": "Backend", "requirements": [{"req_id": "r1", "text": "Kafka",
                                                                         "source_quote": "Kafka"}]}, {"code": "test"})
        job.brief_artifact_id = brief.id
        resume = Resume(user_id=user.id, job_id=job.id, title="Backend")
        session.add(job)
        session.add(resume)
        session.commit()
        session.refresh(resume)
        run = start(session, user.id, "resume_generate", {"resume_id": resume.id, "job_id": job.id})
        step = session.exec(select(WorkflowStep).where(WorkflowStep.run_id == run.id)
                            .order_by(WorkflowStep.ordinal)).first()
        step.status, step.error = "pending", "执行中断，等待重试"
        run.status = "failed"
        session.add(step)
        session.add(run)
        session.commit()
        run_id, step_id = run.id, step.id
    try:
        response = client.post(f"/api/workflows/{run_id}/steps/{step_id}/retry")
        assert response.status_code == 200, response.text
        task = client.get(f"/api/tasks/{response.json()['task_id']}").json()
        assert task["status"] == "done", task
        detail = client.get(f"/api/workflows/{run_id}").json()
        assert [step["status"] for step in detail["steps"]] == ["done", "waiting_user", "pending"]
    finally:
        app.dependency_overrides.clear()


def test_interview_feedback_step_can_retry_without_rewriting_report(monkeypatch, tmp_path):
    client, db, user = _client(monkeypatch, tmp_path)
    monkeypatch.setattr("agents.feedback.extract.propose_requests", lambda *_args: [])
    with Session(db) as session:
        interview = Interview(user_id=user.id, job_id=1, title="Backend", status="finished",
                              report={"risks": ["Kafka evidence"]})
        session.add(interview)
        session.commit()
        session.refresh(interview)
        run = start(session, user.id, "interview", {"interview_id": interview.id, "job_id": 1})
        steps = session.exec(select(WorkflowStep).where(WorkflowStep.run_id == run.id)
                             .order_by(WorkflowStep.ordinal)).all()
        for previous in steps[:-1]:
            previous.status = "done"
            session.add(previous)
        steps[-1].status, steps[-1].error = "pending", "执行中断，等待重试"
        run.status = "failed"
        session.add(steps[-1])
        session.add(run)
        session.commit()
        run_id, step_id = run.id, steps[-1].id
    try:
        response = client.post(f"/api/workflows/{run_id}/steps/{step_id}/retry")
        assert response.status_code == 200, response.text
        detail = client.get(f"/api/workflows/{run_id}").json()
        assert detail["run"]["status"] == "done" and detail["steps"][-1]["status"] == "done"
    finally:
        app.dependency_overrides.clear()
