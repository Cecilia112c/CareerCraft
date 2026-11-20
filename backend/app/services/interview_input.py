"""The ONLY place that decides what the interview agent may see.

Whitelist: JD fields a recruiter publishes + plain resume text + this session's Q&A.
No evidence ids, polish history, rejected patches, JD-agent scores, profile JSON, etc.
"""

from __future__ import annotations

from agents.interview_agent import InterviewInput, validate_input
from sqlmodel import Session
from backend.app.models import Artifact, Interview, Job
from backend.app.services.jobs import job_posting


def interview_job(job: Job) -> dict:
    p = job_posting(job)
    return {"title": p.title or job.title, "company": p.company, "summary": p.summary,
            "requirements": p.requirements, "responsibilities": p.responsibilities,
            "keywords": p.keywords}


def build_input(interview: Interview, job: Job | None, session: Session | None = None) -> InterviewInput:
    if job is None:
        raise ValueError("该面试对应的岗位已被删除")
    from agents.jd_agent.brief import build_brief
    from backend.app.workflows.projections import project_interview_brief
    artifact = session.get(Artifact, interview.brief_artifact_id) if session and interview.brief_artifact_id else None
    if artifact and artifact.user_id == interview.user_id:
        projected = dict(artifact.body)
        projected["history"] = [{"qid": turn.get("qid", ""), "project": turn.get("project", ""),
                                 "question": turn.get("question", ""), "answer": turn.get("answer", ""),
                                 "is_follow_up": bool(turn.get("is_follow_up"))} for turn in interview.turns]
        projected.pop("mode", None)
        return validate_input(projected)
    brief = project_interview_brief(interview, job, build_brief(job_posting(job)).get("requirements", []))
    return validate_input(brief.model_dump(exclude={"mode"}))
