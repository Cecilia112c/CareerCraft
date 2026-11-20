from agents.interview_agent.guard import validate_input
from backend.app.models import Interview, Job
from backend.app.workflows.projections import project_interview_brief


def test_blind_and_contrast_interview_projection_exposes_only_resume_quotes():
    job = Job(title="后端工程师", company="示例公司", data={"title": "后端工程师",
              "requirements": ["熟悉 Python"], "keywords": ["Python"]})
    interview = Interview(mode="blind", resume_text="使用 Python 开发检索服务，并负责接口设计与性能测试。")
    requirements = [{"req_id": "r1", "text": "熟悉 Python", "skills": ["Python"]}]
    blind = project_interview_brief(interview, job, requirements)
    assert blind.job["requirements"] == [] and blind.claimed_coverage == []
    validate_input(blind.model_dump(exclude={"mode"}))
    interview.mode = "contrast"
    contrast = project_interview_brief(interview, job, requirements)
    assert contrast.claimed_coverage[0]["quote"] in interview.resume_text
    assert "evidence_id" not in str(contrast.model_dump())
    validate_input(contrast.model_dump(exclude={"mode"}))
