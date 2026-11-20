"""Generate an explicit JD-to-confirmed-evidence handoff."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from agents.resume_agent.match import match_with_agent
from agents.core.schemas import _text_items
from agents.jd_agent.brief import build_brief
from backend.app.auth import get_current_user
from backend.app.db import get_session
from backend.app.models import Artifact, EvidenceClaim, Job, MaterialRequest, User
from backend.app.workflows.artifacts import save_artifact
from backend.app.workflows.engine import execute_step, start
from backend.app.services.jobs import job_posting
from backend.app.services.jobs import load_profile
from backend.app.services.agent_runtime import agent_ctx
from backend.app.knowledge.retrieval import retrieve_l1_evidence

router = APIRouter(prefix="/api", tags=["evidence"])


@router.get("/jobs/{job_id}/evidence")
def latest_evidence(job_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    job = session.exec(select(Job).where(Job.id == job_id, Job.user_id == user.id)).first()
    if not job:
        raise HTTPException(404, "职位不存在")
    rows = session.exec(select(Artifact).where(Artifact.user_id == user.id,
                                               Artifact.kind == "ResumeEvidence").order_by(Artifact.created_at.desc())).all()
    return next((row for row in rows if row.subject.get("job_id") == job_id), None)


@router.post("/jobs/{job_id}/evidence")
def build_evidence(job_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    job = session.exec(select(Job).where(Job.id == job_id, Job.user_id == user.id)).first()
    if not job:
        raise HTTPException(404, "职位不存在")
    if not job.brief_artifact_id:
        body = build_brief(job_posting(job))
        generated = save_artifact(session, user.id, "JobBrief", {"job_id": job_id}, body,
                                  {"agent": "jd", "spec_id": "jd.normalize", "migration": "existing_job"})
        job.brief_artifact_id = generated.id
        session.add(job)
        session.commit()
    brief = session.exec(select(Artifact).where(Artifact.id == job.brief_artifact_id,
                                                 Artifact.user_id == user.id)).first()
    if not brief:
        raise HTTPException(404, "岗位交接产物不存在")
    candidates = retrieve_l1_evidence(session, user.id, brief.body)
    run = start(session, user.id, "evidence_match", {"job_id": job_id})

    def produce():
        result = match_with_agent({**brief.body, "job_id": job_id}, candidates, agent_ctx(user.id, "resume"))
        artifact = save_artifact(session, user.id, "ResumeEvidence", {"job_id": job_id}, result,
                                 {"agent": "resume", "spec_id": "resume.match", "workflow_id": run.id},
                                 inputs=[{"id": brief.id, "version": brief.version, "content_hash": brief.content_hash}])
        for match in result["matches"]:
            if match["coverage"] != "none":
                continue
            target = {"job_id": job_id, "req_id": match["req_id"]}
            existing = session.exec(select(MaterialRequest).where(MaterialRequest.user_id == user.id,
                                                                   MaterialRequest.status.in_(["proposed", "open"]))).all()
            if any(item.target == target for item in existing):
                continue
            session.add(MaterialRequest(user_id=user.id, target=target, gap_type="requirement",
                                        question=f"你是否有与“{match['requirement']}”相关的真实经历？请写出具体任务、方法和结果。",
                                        priority="medium", origin={"artifact_id": artifact.id}, status="open"))
        session.commit()
        return artifact, f"匹配 {len(result['matches'])} 条要求，缺少 {len(result['missing_req_ids'])} 条依据", [{"id": artifact.id, "version": artifact.version}]

    return execute_step(session, run, "依据已匹配", produce,
                        f"JobBrief v{brief.version} + 检索到 L1 依据 {len(candidates)} 条",
                        [{"id": brief.id, "version": brief.version}])
