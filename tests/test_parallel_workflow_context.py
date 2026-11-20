from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from agents.core.runner import parallel_map
from backend.app.workflows.engine import current_step_id, execute_step, start


def test_parallel_project_calls_keep_workflow_step_context():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        run = start(session, 1, "resume_generate", {"resume_id": 1})
        result = execute_step(session, run, "定向简历已生成",
                              lambda: (parallel_map(lambda _: current_step_id(), range(3)), "完成", []))
        assert result == [result[0]] * 3
        assert result[0].startswith("step_")
