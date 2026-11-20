from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from agents.core.schemas import ResumeDoc, full_text, _text_items
from agents.resume_agent.match import match_with_agent
from agents.resume_agent import POLISH_MODES, expand_scope, generate_resume, polish_selection, render_html
from backend.app.auth import get_current_user, get_owned
from backend.app.db import engine, get_session
from backend.app.models import Artifact, EvidenceClaim, Job, MaterialRequest, Resume, ResumePatchFeedback, ResumeVersion, User, WorkflowRun
from backend.app.workflows.artifacts import save_artifact
from backend.app.workflows.engine import execute_step, resume_gate, skip_gate, start, wait_gate
from backend.app.services.export import ExportError, export_html, export_pdf
from backend.app.services.jobs import job_posting, load_profile
from backend.app.services.resume_ops import (
    add_version, apply_patches, apply_sync, get_version, save_profile, sync_diff,
)
from backend.app.services.agent_runtime import agent_ctx
from backend.app.services.tasks import submit
from backend.app.services.evidence import validate_resume_citations
from backend.app.knowledge.retrieval import retrieve_l1_evidence

router = APIRouter(prefix="/api", tags=["resumes"])


class CreateBody(BaseModel):
    job_id: int | None = None
    title: str = ""


class SaveBody(BaseModel):
    base_version: int
    data: dict
    note: str = "手动编辑"


class PolishBody(BaseModel):
    version: int
    ids: list[str] = Field(min_length=1, max_length=40)        # 句子 id 或模块 id（项目/经历/教育）
    instruction: str = Field(default="", max_length=800)       # 用户指令
    mode: str = "custom"                                       # 快捷按钮（可选）
    scope_label: str = Field(default="", max_length=80)        # 例如“项目：订单系统重构”
    data: dict | None = None                                   # 页面上当前的简历内容（可能尚未保存）


class PatchItem(BaseModel):
    id: str
    new: str


class ApplyBody(BaseModel):
    base_version: int
    patches: list[PatchItem] = Field(min_length=1)


class RollbackBody(BaseModel):
    version: int


class RenderBody(BaseModel):
    data: dict
    interactive: bool = True


class SyncBody(BaseModel):
    version: int
    keys: list[str] = Field(min_length=1)
    proposal_id: str = ""


class PatchFeedbackBody(BaseModel):
    patch_id: str = Field(min_length=1, max_length=80)
    reason: str


FEEDBACK_PREFERENCES = {
    "verbose": "简历润色优先简洁表达，避免冗长句子。",
    "tone": "简历润色保持自然、克制的语气，避免夸张措辞。",
    "unfaithful": "简历润色严格保留我原有的职责边界，不扩大个人贡献。",
}


def _resume_dict(session: Session, r: Resume) -> dict:
    job = session.get(Job, r.job_id) if r.job_id else None
    artifact = session.get(Artifact, r.artifact_id) if r.artifact_id else None
    return {"id": r.id, "title": r.title, "job_id": r.job_id,
            "job_title": f"{job.title}｜{job.company}" if job else "",
            "current_version": r.current_version, "artifact_status": artifact.status if artifact else "unknown",
            "updated_at": r.updated_at.isoformat(),
            "created_at": r.created_at.isoformat()}


def record_resume_draft(session: Session, user_id: int, resume: Resume, version: ResumeVersion) -> Artifact:
    job = session.get(Job, resume.job_id) if resume.job_id else None
    brief = session.get(Artifact, job.brief_artifact_id) if job and job.brief_artifact_id else None
    inputs = [{"id": brief.id, "version": brief.version, "content_hash": brief.content_hash}] if brief else []
    matches = session.exec(select(Artifact).where(Artifact.user_id == user_id,
                                                  Artifact.kind == "ResumeEvidence",
                                                  Artifact.status == "active").order_by(Artifact.created_at.desc())).all()
    matched = next((row for row in matches if row.subject.get("job_id") == resume.job_id), None)
    if matched:
        inputs.append({"id": matched.id, "version": matched.version, "content_hash": matched.content_hash})
        version.evidence_artifact_id = matched.id
        session.add(version)
    artifact = save_artifact(session, user_id, "ResumeDraft", {"resume_id": resume.id},
                             {"resume_version": version.version, "job_id": resume.job_id},
                             {"agent": "resume", "spec_id": "resume.version"}, inputs=inputs)
    resume.artifact_id = artifact.id
    session.add(resume)
    session.commit()
    return artifact


def _generate_in_workflow(session: Session, run: WorkflowRun, resume_id: int, user_id: int, report) -> dict:
    resume = session.get(Resume, resume_id)
    profile = load_profile(session, user_id)
    job = session.get(Job, resume.job_id) if resume.job_id else None
    posting = job_posting(job) if job else None
    claims = session.exec(select(EvidenceClaim).where(EvidenceClaim.user_id == user_id,
                                                     EvidenceClaim.status == "confirmed",
                                                     EvidenceClaim.level == "L1")).all()
    generation_evidence = [{"id": f"claim:{claim.id}", "statement": claim.statement,
                            "project_id": claim.project_id} for claim in claims if claim.project_id]
    def produce():
        out = generate_resume(profile, posting, job_id=resume.job_id, report=report,
                              ctx=agent_ctx(user_id, "resume", session=f"resume:{resume_id}"),
                              confirmed_evidence=generation_evidence)
        validate_resume_citations(session, user_id, out.resume)
        version = add_version(session, resume, out.resume, "AI 生成（STAR 润色）")
        artifact = record_resume_draft(session, user_id, resume, version)
        return {"resume_id": resume_id, "version": version.version, "warnings": out.warnings}, \
            f"ResumeDraft v{version.version}", [{"id": artifact.id, "version": artifact.version}]
    return execute_step(session, run, "定向简历已生成", produce,
                        f"资料 + 职位 {resume.job_id or '通用'}", node_type="agent")


def _retry_match_in_workflow(session: Session, run: WorkflowRun, resume_id: int, user_id: int, report) -> dict:
    """Continue an interrupted evidence match on the original workflow."""
    resume = session.get(Resume, resume_id)
    if not resume or resume.user_id != user_id or not resume.job_id:
        raise ValueError("定向简历或职位不存在")
    job = session.get(Job, resume.job_id)
    brief = session.get(Artifact, job.brief_artifact_id) if job and job.brief_artifact_id else None
    if not brief:
        raise ValueError("职位交接产物不存在")
    facts = retrieve_l1_evidence(session, user_id, brief.body)
    def match():
        result = match_with_agent({**brief.body, "job_id": job.id}, facts,
                                  agent_ctx(user_id, "resume", session=f"resume:{resume_id}"))
        artifact = save_artifact(session, user_id, "ResumeEvidence", {"job_id": job.id}, result,
                                 {"agent": "resume", "spec_id": "resume.match", "workflow_id": run.id},
                                 inputs=[{"id": brief.id, "version": brief.version,
                                          "content_hash": brief.content_hash}])
        existing = session.exec(select(MaterialRequest).where(MaterialRequest.user_id == user_id,
                                                               MaterialRequest.status.in_(["open", "proposed"]))).all()
        for item in result["matches"]:
            if item["coverage"] != "none":
                continue
            target = {"job_id": job.id, "req_id": item["req_id"]}
            if any(request.target == target for request in existing):
                continue
            request = MaterialRequest(user_id=user_id, target=target, gap_type="requirement",
                                      question=f"你是否有与“{item['requirement']}”相关的真实经历？请写出任务、方法和结果。",
                                      priority="medium", origin={"artifact_id": artifact.id}, status="open")
            session.add(request)
            existing.append(request)
        session.commit()
        return artifact, f"匹配 {len(result['matches'])} 条要求，缺少 {len(result['missing_req_ids'])} 条依据", \
            [{"id": artifact.id, "version": artifact.version}]
    matched = execute_step(session, run, "依据已匹配", match,
                           f"JobBrief v{brief.version} + L1 依据 {len(facts)} 条",
                           [{"id": brief.id, "version": brief.version}], terminal=False, node_type="agent")
    missing = matched.body.get("missing_req_ids", [])
    if missing:
        wait_gate(session, run, "等待补充资料", f"{len(missing)} 条岗位要求缺少依据，可补充或跳过继续生成",
                  [{"id": matched.id, "version": matched.version}])
        return {"resume_id": resume_id, "waiting_user": True,
                "workflow_id": run.id, "missing_req_ids": missing}
    skip_gate(session, run, "等待补充资料", "岗位要求均有候选依据")
    return _generate_in_workflow(session, run, resume_id, user_id, report)


@router.post("/resumes")
def create_resume(body: CreateBody, background: BackgroundTasks, user: User = Depends(get_current_user),
                  session: Session = Depends(get_session)):
    profile = load_profile(session, user.id)
    if len(full_text(profile)) < 30:
        raise HTTPException(400, "个人资料内容太少，请先完善“我的资料”")
    job = get_owned(session, Job, body.job_id, user) if body.job_id else None
    if job and job.detail_level == "summary":
        raise HTTPException(400, "该职位只有摘要，请先收藏完整职位描述")
    title = body.title or (f"{job.title}｜{job.company}" if job else "通用简历")
    resume = Resume(user_id=user.id, job_id=job.id if job else None, title=title[:80])
    session.add(resume)
    session.commit()
    session.refresh(resume)
    resume_id, user_id = resume.id, user.id
    def work(report):
        with Session(engine) as s:
            run = start(s, user_id, "resume_generate", {"resume_id": resume_id, "job_id": resume.job_id})
            if resume.job_id:
                job_row = s.get(Job, resume.job_id)
                brief = s.get(Artifact, job_row.brief_artifact_id) if job_row.brief_artifact_id else None
                if not brief:
                    from agents.jd_agent.brief import build_brief
                    brief = save_artifact(s, user_id, "JobBrief", {"job_id": job_row.id},
                                          build_brief(job_posting(job_row)),
                                          {"agent": "jd", "spec_id": "jd.normalize", "workflow_id": run.id})
                    job_row.brief_artifact_id = brief.id
                    s.add(job_row)
                    s.commit()
                facts = retrieve_l1_evidence(s, user_id, brief.body)
                def match():
                    result = match_with_agent({**brief.body, "job_id": job_row.id}, facts,
                                              agent_ctx(user_id, "resume", session=f"resume:{resume_id}"))
                    artifact = save_artifact(s, user_id, "ResumeEvidence", {"job_id": job_row.id}, result,
                                             {"agent": "resume", "spec_id": "resume.match", "workflow_id": run.id},
                                             inputs=[{"id": brief.id, "version": brief.version,
                                                      "content_hash": brief.content_hash}])
                    existing = s.exec(select(MaterialRequest).where(MaterialRequest.user_id == user_id,
                                                                       MaterialRequest.status.in_(["open", "proposed"]))).all()
                    for item in result["matches"]:
                        if item["coverage"] != "none":
                            continue
                        target = {"job_id": job_row.id, "req_id": item["req_id"]}
                        if any(request.target == target for request in existing):
                            continue
                        request = MaterialRequest(user_id=user_id, target=target, gap_type="requirement",
                                                  question=f"你是否有与“{item['requirement']}”相关的真实经历？请写出任务、方法和结果。",
                                                  priority="medium", origin={"artifact_id": artifact.id}, status="open")
                        s.add(request)
                        existing.append(request)
                    s.commit()
                    return artifact, f"匹配 {len(result['matches'])} 条要求，缺少 {len(result['missing_req_ids'])} 条依据", \
                        [{"id": artifact.id, "version": artifact.version}]
                matched = execute_step(s, run, "依据已匹配", match,
                                       f"JobBrief v{brief.version} + L1 依据 {len(facts)} 条",
                                       [{"id": brief.id, "version": brief.version}], terminal=False)
                missing = matched.body.get("missing_req_ids", [])
                if missing:
                    wait_gate(s, run, "等待补充资料", f"{len(missing)} 条岗位要求缺少依据，可补充或跳过继续生成",
                              [{"id": matched.id, "version": matched.version}])
                    return {"resume_id": resume_id, "waiting_user": True,
                            "workflow_id": run.id, "missing_req_ids": missing}
                skip_gate(s, run, "等待补充资料", "岗位要求均有候选依据")
            return _generate_in_workflow(s, run, resume_id, user_id, report)

    task = submit(background, session, user_id, "resume:generate", work)
    return {"resume_id": resume_id, "task_id": task.id}


@router.get("/resumes")
def list_resumes(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    rows = session.exec(select(Resume).where(Resume.user_id == user.id)
                        .order_by(Resume.updated_at.desc())).all()
    return [_resume_dict(session, r) for r in rows]


@router.get("/resumes/{resume_id}")
def get_resume(resume_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    r = get_owned(session, Resume, resume_id, user)
    versions = session.exec(select(ResumeVersion).where(ResumeVersion.resume_id == r.id)
                            .order_by(ResumeVersion.version.desc())).all()
    current = next((v for v in versions if v.version == r.current_version), None)
    return {**_resume_dict(session, r),
            "versions": [{"version": v.version, "note": v.note, "created_at": v.created_at.isoformat()}
                         for v in versions],
            "current": {"version": current.version, "data": current.data} if current else None}


@router.delete("/resumes/{resume_id}")
def delete_resume(resume_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    r = get_owned(session, Resume, resume_id, user)
    for v in session.exec(select(ResumeVersion).where(ResumeVersion.resume_id == r.id)).all():
        session.delete(v)
    session.delete(r)
    session.commit()
    return {"ok": True}


@router.get("/resumes/{resume_id}/versions/{version}")
def get_resume_version(resume_id: int, version: int, user: User = Depends(get_current_user),
                       session: Session = Depends(get_session)):
    r = get_owned(session, Resume, resume_id, user)
    v = get_version(session, r, version)
    return {"version": v.version, "note": v.note, "data": v.data}


@router.get("/resumes/{resume_id}/versions/{version}/citations")
def resume_citations(resume_id: int, version: int, user: User = Depends(get_current_user),
                     session: Session = Depends(get_session)):
    resume = get_owned(session, Resume, resume_id, user)
    doc = ResumeDoc.model_validate(get_version(session, resume, version).data)
    profile = load_profile(session, user.id)
    profile_items = {f"profile:{item.id}": item.text for item in _text_items(profile)}
    claims = session.exec(select(EvidenceClaim).where(EvidenceClaim.user_id == user.id,
                                                     EvidenceClaim.status == "confirmed",
                                                     EvidenceClaim.level == "L1")).all()
    evidence = {**profile_items, **{f"claim:{c.id}": c.statement for c in claims}}
    evidence.update({"profile:basic.headline": profile.basic.headline,
                     "profile:basic.summary": profile.basic.summary,
                     "profile:skills": "、".join(profile.skills)})
    entries = [(item.id, item.text, item.evidence_ids) for item in _text_items(doc)]
    entries += [("basic.headline", doc.basic.headline, doc.basic.headline_evidence_ids),
                ("basic.summary", doc.basic.summary, doc.basic.summary_evidence_ids)]
    return [{"sentence_id": item_id, "text": value,
             "citations": [{"id": ref, "statement": evidence.get(ref), "valid": ref in evidence}
                           for ref in refs]}
            for item_id, value, refs in entries if refs]


@router.post("/resumes/{resume_id}/versions")
def save_version(resume_id: int, body: SaveBody, user: User = Depends(get_current_user),
                 session: Session = Depends(get_session)):
    r = get_owned(session, Resume, resume_id, user)
    doc = ResumeDoc.model_validate(body.data)
    validate_resume_citations(session, user.id, doc)
    v = add_version(session, r, doc, body.note[:60] or "手动编辑", base_version=body.base_version)
    record_resume_draft(session, user.id, r, v)
    return {"version": v.version, "data": v.data}


@router.post("/resumes/{resume_id}/polish")
def polish(resume_id: int, body: PolishBody, background: BackgroundTasks,
           user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    r = get_owned(session, Resume, resume_id, user)
    if body.mode not in POLISH_MODES:
        raise HTTPException(400, "未知的修改方式")
    if body.mode == "custom" and not body.instruction.strip():
        raise HTTPException(400, "请输入修改指令")
    source = body.data if body.data is not None else get_version(session, r, body.version).data
    doc = ResumeDoc.model_validate(source)
    if not expand_scope(doc, body.ids):
        raise HTTPException(400, "所选范围内没有可修改的正文")
    profile = load_profile(session, user.id)
    job_row = session.get(Job, r.job_id) if r.job_id else None
    posting = job_posting(job_row) if job_row else None
    confirmed = session.exec(select(EvidenceClaim).where(EvidenceClaim.user_id == user.id,
                                                         EvidenceClaim.status == "confirmed",
                                                         EvidenceClaim.level == "L1")).all()
    evidence = [{"id": f"claim:{c.id}", "statement": c.statement} for c in confirmed]
    ctx = agent_ctx(user.id, "resume", session=f"resume:{resume_id}", instruction=body.instruction)

    def work(report):
        out = polish_selection(doc, profile, body.ids, body.mode, body.instruction, posting, report=report,
                               ctx=ctx, scope_label=body.scope_label, confirmed_evidence=evidence)
        return {**out.model_dump(mode="json"), "base_version": body.version}

    return {"task_id": submit(background, session, user.id, "resume:polish", work).id}


@router.post("/resumes/{resume_id}/refresh")
def refresh_resume(resume_id: int, background: BackgroundTasks, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)):
    resume = get_owned(session, Resume, resume_id, user)
    artifact = session.get(Artifact, resume.artifact_id) if resume.artifact_id else None
    if not artifact or artifact.status != "stale":
        raise HTTPException(409, "当前简历没有过期依据")
    version = resume.current_version
    doc = ResumeDoc.model_validate(get_version(session, resume, version).data)
    ids = [item.id for item in _text_items(doc) if item.text.strip()][:30]
    if not ids:
        raise HTTPException(400, "没有可检查的正文")
    user_id = user.id
    def work(report):
        with Session(engine) as s:
            row = s.get(Resume, resume_id)
            latest = ResumeDoc.model_validate(get_version(s, row, version).data)
            profile = load_profile(s, user_id)
            job = s.get(Job, row.job_id) if row.job_id else None
            claims = s.exec(select(EvidenceClaim).where(EvidenceClaim.user_id == user_id,
                                                       EvidenceClaim.status == "confirmed",
                                                       EvidenceClaim.level == "L1")).all()
            facts = [{"id": f"claim:{claim.id}", "statement": claim.statement,
                      "project_id": claim.project_id} for claim in claims]
            out = polish_selection(latest, profile, ids, "custom",
                                   "依据已更新。只用最新资料和已确认事实，逐句检查可更新的内容；没有真实依据时保留原句并指出需要补充什么。",
                                   job_posting(job) if job else None, report=report,
                                   ctx=agent_ctx(user_id, "resume", session=f"resume:{resume_id}"),
                                   confirmed_evidence=facts)
            existing = s.exec(select(MaterialRequest).where(MaterialRequest.user_id == user_id,
                                                               MaterialRequest.status == "open")).all()
            for question in out.needs_confirmation[:10]:
                target = {"resume_id": resume_id, "question": question}
                if not any(item.target == target for item in existing):
                    s.add(MaterialRequest(user_id=user_id, target=target, gap_type="resume_refresh",
                                          question=question, origin={"resume_id": resume_id}, status="open"))
            s.commit()
            return {**out.model_dump(mode="json"), "base_version": version}
    return {"task_id": submit(background, session, user.id, "resume:refresh", work).id}


@router.post("/resumes/{resume_id}/patch-feedback")
def patch_feedback(resume_id: int, body: PatchFeedbackBody, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)):
    get_owned(session, Resume, resume_id, user)
    if body.reason not in FEEDBACK_PREFERENCES:
        raise HTTPException(422, "未知的反馈原因")
    previous = session.exec(select(ResumePatchFeedback).where(ResumePatchFeedback.user_id == user.id,
                                                               ResumePatchFeedback.reason == body.reason)).all()
    if any(row.resume_id == resume_id and row.patch_id == body.patch_id for row in previous):
        return {"count": len(previous), "preference_proposal": None}
    session.add(ResumePatchFeedback(user_id=user.id, resume_id=resume_id,
                                    patch_id=body.patch_id, reason=body.reason))
    session.commit()
    count = len(previous) + 1
    proposal = None
    if count >= 3:
        from backend.app.services.agent_runtime import memory
        proposal = memory().preferences.propose(str(user.id), "resume", FEEDBACK_PREFERENCES[body.reason],
                                                 key=f"feedback.{body.reason}", source="repeated_patch_rejection",
                                                 evidence=f"{count} 次同类改写被跳过")
    return {"count": count, "preference_proposal": proposal.as_dict() if proposal else None}


@router.post("/resumes/{resume_id}/apply-patches")
def apply(resume_id: int, body: ApplyBody, user: User = Depends(get_current_user),
          session: Session = Depends(get_session)):
    r = get_owned(session, Resume, resume_id, user)
    doc = ResumeDoc.model_validate(get_version(session, r, body.base_version).data)
    n = apply_patches(doc, [p.model_dump() for p in body.patches])
    if n == 0:
        raise HTTPException(400, "没有可应用的修改")
    v = add_version(session, r, doc, f"AI 润色（{n} 处）", base_version=body.base_version)
    record_resume_draft(session, user.id, r, v)
    return {"version": v.version, "data": v.data}


@router.post("/resumes/{resume_id}/rollback")
def rollback(resume_id: int, body: RollbackBody, user: User = Depends(get_current_user),
             session: Session = Depends(get_session)):
    r = get_owned(session, Resume, resume_id, user)
    doc = ResumeDoc.model_validate(get_version(session, r, body.version).data)
    v = add_version(session, r, doc, f"回滚到 v{body.version}")
    record_resume_draft(session, user.id, r, v)
    return {"version": v.version, "data": v.data}


@router.post("/render", response_class=HTMLResponse)
def render(body: RenderBody, user: User = Depends(get_current_user)):  # noqa: ARG001
    return HTMLResponse(render_html(ResumeDoc.model_validate(body.data), interactive=body.interactive))


@router.get("/resumes/{resume_id}/versions/{version}/export")
def export(resume_id: int, version: int, format: str = "html", user: User = Depends(get_current_user),
           session: Session = Depends(get_session)):
    r = get_owned(session, Resume, resume_id, user)
    doc = ResumeDoc.model_validate(get_version(session, r, version).data)
    name = f"{doc.basic.name or '简历'}_{r.title}_v{version}".replace("/", "-")[:60]
    try:
        if format == "pdf":
            content, media, ext = export_pdf(doc), "application/pdf", "pdf"
        else:
            content, media, ext = export_html(doc), "text/html; charset=utf-8", "html"
    except ExportError as exc:
        raise HTTPException(500, str(exc))
    disposition = f"attachment; filename=resume.{ext}; filename*=UTF-8''{quote(name)}.{ext}"
    return Response(content=content, media_type=media, headers={"Content-Disposition": disposition})


@router.get("/resumes/{resume_id}/sync-diff")
def get_sync_diff(resume_id: int, version: int, user: User = Depends(get_current_user),
                  session: Session = Depends(get_session)):
    r = get_owned(session, Resume, resume_id, user)
    doc = ResumeDoc.model_validate(get_version(session, r, version).data)
    return sync_diff(doc, load_profile(session, user.id))


@router.post("/resumes/{resume_id}/sync-proposal")
def create_sync_proposal(resume_id: int, version: int, user: User = Depends(get_current_user),
                         session: Session = Depends(get_session)):
    r = get_owned(session, Resume, resume_id, user)
    doc = ResumeDoc.model_validate(get_version(session, r, version).data)
    diffs = sync_diff(doc, load_profile(session, user.id))
    artifact = save_artifact(session, user.id, "ProfileUpdateProposal",
                             {"resume_id": resume_id, "version": version},
                             {"resume_id": resume_id, "version": version, "diffs": diffs, "status": "proposed"},
                             {"code": "resume.sync_diff"},
                             inputs=[{"id": r.artifact_id}] if r.artifact_id else [])
    return artifact


@router.post("/resumes/{resume_id}/sync")
def do_sync(resume_id: int, body: SyncBody, user: User = Depends(get_current_user),
            session: Session = Depends(get_session)):
    r = get_owned(session, Resume, resume_id, user)
    doc = ResumeDoc.model_validate(get_version(session, r, body.version).data)
    profile = load_profile(session, user.id)
    proposal = None
    if body.proposal_id:
        proposal = session.exec(select(Artifact).where(Artifact.id == body.proposal_id,
                                                       Artifact.user_id == user.id,
                                                       Artifact.kind == "ProfileUpdateProposal")).first()
        if not proposal or proposal.status != "active" or proposal.subject != {"resume_id": resume_id,
                                                                                "version": body.version}:
            raise HTTPException(409, "资料更新提议已失效，请重新查看差异")
        current = {diff["key"]: diff for diff in sync_diff(doc, profile)}
        proposed = {diff["key"]: diff for diff in proposal.body["diffs"]}
        if any(key not in proposed or current.get(key) != proposed[key] for key in body.keys):
            raise HTTPException(409, "资料已发生变化，请重新查看差异")
    n = apply_sync(doc, profile, body.keys)
    save_profile(session, user.id, profile)
    if proposal:
        proposal.status = "superseded"
        session.add(proposal)
    r.updated_at = datetime.now(timezone.utc)
    session.add(r)
    session.commit()
    return {"applied": n}
