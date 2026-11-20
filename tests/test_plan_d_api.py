"""A material becomes a proposed fact, then an L1 fact only after user action."""

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.auth import get_current_user
from backend.app.db import get_session
from backend.app.main import app
from backend.app.models import EvidenceClaim, Job, Profile, User, WorkflowRun


def test_note_ingest_gate_and_batch_confirmation(monkeypatch, llm):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(username="plan-d-test", password_hash="x")
        session.add(user)
        session.commit()
        session.refresh(user)

    def test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = test_session
    monkeypatch.setattr("backend.app.routers.knowledge.engine", engine)
    monkeypatch.setattr("backend.app.services.tasks.engine", engine)
    llm.push({"claims": [{"statement": "使用 Python 开发检索服务", "claim_type": "skill",
                           "quote": "使用 Python 开发检索服务"}]})
    try:
        client = TestClient(app)
        response = client.post("/api/knowledge/sources/note",
                               json={"title": "检索项目", "text": "使用 Python 开发检索服务"})
        assert response.status_code == 200, response.text
        task = client.get(f"/api/tasks/{response.json()['task_id']}").json()
        assert task["status"] == "done", task
        claims = client.get("/api/knowledge/claims").json()
        assert len(claims) == 1 and claims[0]["level"] == "L2"
        assert client.post("/api/knowledge/claims/batch",
                           json={"ids": [claims[0]["id"]], "action": "confirm"}).status_code == 200
        with Session(engine) as session:
            claim = session.exec(select(EvidenceClaim)).one()
            workflow = session.exec(select(WorkflowRun)).one()
            assert claim.level == "L1" and claim.status == "confirmed"
            assert workflow.status == "done"
    finally:
        app.dependency_overrides.clear()


def test_resume_workflow_stops_at_missing_evidence_gate(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(username="resume-gate", password_hash="x")
        session.add(user)
        session.commit()
        session.refresh(user)
        session.add(Profile(user_id=user.id, data={"basic": {"summary": "参与多个校园项目，负责需求分析、文档整理、接口开发和功能测试。"}}))
        session.add(Job(user_id=user.id, title="机器学习工程师", detail_level="full",
                        data={"title": "机器学习工程师", "requirements": ["熟悉 CUDA 内核优化"],
                              "keywords": ["CUDA"]}))
        session.commit()
        user = User(id=user.id, username="resume-gate", password_hash="x")

    def test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = test_session
    monkeypatch.setattr("backend.app.routers.resumes.engine", engine)
    monkeypatch.setattr("backend.app.services.tasks.engine", engine)
    try:
        client = TestClient(app)
        job = client.get("/api/jobs").json()[0]
        response = client.post("/api/resumes", json={"job_id": job["id"]})
        assert response.status_code == 200, response.text
        task = client.get(f"/api/tasks/{response.json()['task_id']}").json()
        assert task["status"] == "done", task
        assert task["result"]["waiting_user"] is True
        run = client.get(f"/api/workflows/{task['result']['workflow_id']}").json()
        assert run["run"]["status"] == "waiting_user"
        assert [step["status"] for step in run["steps"]] == ["done", "waiting_user", "pending"]
    finally:
        app.dependency_overrides.clear()


def test_clipped_detail_creates_job_brief_and_timeline():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(username="clip-brief", password_hash="x")
        session.add(user)
        session.commit()
        session.refresh(user)
        session.add(Profile(user_id=user.id, data={}))
        session.commit()
        user = User(id=user.id, username="clip-brief", password_hash="x")

    def test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = test_session
    try:
        client = TestClient(app)
        detail = {"title": "后端开发", "company": "示例公司", "area": "北京", "salary": "",
                  "url": "https://www.zhipin.com/job_detail/123.html",
                  "description": "岗位要求：熟悉 Python 开发，负责接口设计和性能优化，能够独立完成模块开发。",
                  "requirements": ["熟悉 Python 开发"], "responsibilities": ["负责接口设计"]}
        response = client.post("/api/clip/save", json={"detail": detail})
        assert response.status_code == 200, response.text
        job_id = response.json()["job_ids"][0]
        brief = client.get(f"/api/jobs/{job_id}/brief")
        assert brief.status_code == 200
        assert brief.json()["body"]["requirements"][0]["source_quote"] in detail["description"]
        runs = client.get("/api/workflows", params={"subject": f"job_id:{job_id}"}).json()
        assert runs and runs[0]["status"] == "done"
    finally:
        app.dependency_overrides.clear()


def test_pasted_jd_links_model_run_to_workflow_step(monkeypatch, llm):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(username="paste-brief", password_hash="x")
        session.add(user)
        session.commit()
        session.refresh(user)
        session.add(Profile(user_id=user.id, data={}))
        session.commit()
        user = User(id=user.id, username="paste-brief", password_hash="x")

    def test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = test_session
    monkeypatch.setattr("backend.app.routers.jobs.engine", engine)
    monkeypatch.setattr("backend.app.services.tasks.engine", engine)
    llm.push({"is_job_page": True, "title": "后端开发", "company": "示例公司",
              "requirements": ["熟悉 Python 开发"], "keywords": ["Python"]})
    try:
        client = TestClient(app)
        response = client.post("/api/jobs/import", json={"text": "招聘后端开发工程师，要求熟悉 Python 开发，负责接口设计与系统维护。"})
        assert response.status_code == 200, response.text
        task = client.get(f"/api/tasks/{response.json()['task_id']}").json()
        assert task["status"] == "done", task
        job_id = task["result"]["job_ids"][0]
        runs = client.get("/api/workflows", params={"subject": f"job_id:{job_id}"}).json()
        detail = client.get(f"/api/workflows/{runs[0]['id']}").json()
        assert detail["steps"][0]["agent_run_ids"]
    finally:
        app.dependency_overrides.clear()
