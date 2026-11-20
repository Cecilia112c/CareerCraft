from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from agents.core.schemas import ResumeDoc, doc_to_text
from agents.interview_agent import Question, diagnose, evaluate_answer, final_report, plan_questions
from backend.app.auth import get_current_user, get_owned
from backend.app.db import engine, get_session
from backend.app.models import Document, Interview, Job, Resume, User
from backend.app.models import Artifact, MaterialRequest, WorkflowRun
from backend.app.workflows.artifacts import save_artifact
from backend.app.workflows.engine import execute_step, resume_gate, start, wait_gate
from agents.feedback.extract import propose_requests
from backend.app.services.agent_runtime import agent_ctx
from backend.app.services.interview_input import build_input
from backend.app.services.jobs import load_profile
from backend.app.services.resume_ops import get_version
from backend.app.services.tasks import submit

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


class Source(BaseModel):
    type: Literal["document", "resume", "profile"]
    id: int | None = None
    version: int | None = None


class CreateBody(BaseModel):
    job_id: int
    source: Source
    total: int = Field(default=10, ge=4, le=20)
    mode: Literal["blind", "contrast"] = "blind"


class AnswerBody(BaseModel):
    text: str = Field(default="", max_length=4000)


def _dict(i: Interview, full: bool = True) -> dict:
    base = {"id": i.id, "title": i.title, "job_id": i.job_id, "source_label": i.source_label,
            "status": i.status, "created_at": i.created_at.isoformat(),
            "answered": len(i.turns), "total": len(i.questions), "round": i.round,
            "previous_interview_id": i.previous_interview_id, "mode": i.mode,
            "brief_artifact_id": i.brief_artifact_id}
    if full:
        base.update({"resume_text": i.resume_text, "gap_report": i.gap_report, "questions": i.questions,
                     "turns": i.turns, "state": i.state, "report": i.report})
    return base


def _resume_text(session: Session, user: User, source: Source) -> tuple[str, str]:
    if source.type == "document":
        doc = get_owned(session, Document, source.id, user)
        return doc.text, f"上传的 PDF：{doc.filename}"
    if source.type == "resume":
        r = get_owned(session, Resume, source.id, user)
        v = get_version(session, r, source.version)
        return doc_to_text(ResumeDoc.model_validate(v.data)), f"简历：{r.title} v{v.version}"
    return doc_to_text(load_profile(session, user.id)), "我的资料"


def _project_brief_step(session: Session, run: WorkflowRun, interview_id: int, user_id: int) -> None:
    from agents.jd_agent.brief import build_brief
    from backend.app.workflows.projections import project_interview_brief
    from backend.app.services.jobs import job_posting
    interview = session.get(Interview, interview_id)
    job = session.get(Job, interview.job_id)
    def project():
        brief = session.get(Artifact, job.brief_artifact_id) if job.brief_artifact_id else None
        requirements = (brief.body if brief else build_brief(job_posting(job))).get("requirements", [])
        projection = project_interview_brief(interview, job, requirements)
        inputs = ([{"id": brief.id, "version": brief.version,
                    "content_hash": brief.content_hash}] if brief else [])
        if interview.source_type == "resume" and interview.source_id:
            drafts = session.exec(select(Artifact).where(Artifact.user_id == user_id,
                                                        Artifact.kind == "ResumeDraft")).all()
            draft = next((item for item in drafts if item.subject.get("resume_id") == interview.source_id
                          and item.body.get("resume_version") == interview.source_version), None)
            if draft:
                inputs.append({"id": draft.id, "version": draft.version, "content_hash": draft.content_hash})
        artifact = save_artifact(session, user_id, "InterviewBrief", {"interview_id": interview.id},
                                 projection.model_dump(),
                                 {"agent": "coordinator", "spec_id": "interview.project", "workflow_id": run.id},
                                 inputs=inputs)
        interview.brief_artifact_id = artifact.id
        session.add(interview)
        session.commit()
        return artifact, f"{interview.mode} 模式；简历 {len(interview.resume_text)} 字", \
            [{"id": artifact.id, "version": artifact.version}]
    execute_step(session, run, "面试视图已生成", project, "岗位 + 简历文本", terminal=False)


def _prepare_questions_step(session: Session, run: WorkflowRun, interview_id: int,
                            user_id: int, total: int, report) -> int:
    interview = session.get(Interview, interview_id)
    job = session.get(Job, interview.job_id)
    def prepare():
        inp = build_input(interview, job, session)
        ctx = agent_ctx(user_id, "interview", session=f"interview:{interview_id}")
        gaps = diagnose(inp, report=report, ctx=ctx)
        questions = plan_questions(inp, gaps, total=total, report=report, ctx=ctx)
        qs = [q.model_dump() for q in questions]
        interview.gap_report = gaps.model_dump()
        interview.questions = qs
        interview.state = {"index": 0, "follow_count": 0, "current": qs[0] if qs else None}
        interview.status = "ongoing" if qs else "answered_all"
        session.add(interview)
        session.flush()
        return len(qs), f"诊断完成，生成 {len(qs)} 道题", []
    count = execute_step(session, run, "诊断与问题已生成", prepare,
                         f"InterviewBrief {interview.brief_artifact_id}", terminal=False, node_type="agent")
    wait_gate(session, run, "等待面试回答", f"已生成 {count} 道题，等待用户回答")
    return count


@router.post("")
def create(body: CreateBody, background: BackgroundTasks, user: User = Depends(get_current_user),
           session: Session = Depends(get_session)):
    job = get_owned(session, Job, body.job_id, user)
    if job.detail_level == "summary":
        raise HTTPException(400, "该职位只有摘要，请先收藏完整职位描述")
    text, label = _resume_text(session, user, body.source)
    if len(text.strip()) < 50:
        raise HTTPException(400, "简历内容太少，无法进行面试")
    selected_version = body.source.version
    if body.source.type == "resume":
        selected_version = get_owned(session, Resume, body.source.id, user).current_version if selected_version is None else selected_version
    interview = Interview(user_id=user.id, job_id=job.id, title=f"{job.title}｜{job.company}"[:80],
                          source_label=label, resume_text=text[:20000], source_type=body.source.type,
                          source_id=body.source.id, source_version=selected_version, mode=body.mode)
    session.add(interview)
    session.commit()
    session.refresh(interview)
    interview_id, total, job_id, user_id = interview.id, body.total, job.id, user.id

    def work(report):
        try:
            with Session(engine) as s:
                i, j = s.get(Interview, interview_id), s.get(Job, job_id)
                from agents.jd_agent.brief import build_brief
                from backend.app.workflows.projections import project_interview_brief
                from backend.app.services.jobs import job_posting
                run = start(s, user_id, "interview", {"interview_id": interview_id, "job_id": job_id,
                                                      "question_total": total})
                def project():
                    brief = s.get(Artifact, j.brief_artifact_id) if j.brief_artifact_id else None
                    requirements = (brief.body if brief else build_brief(job_posting(j))).get("requirements", [])
                    projection = project_interview_brief(i, j, requirements)
                    inputs = ([{"id": brief.id, "version": brief.version,
                                "content_hash": brief.content_hash}] if brief else [])
                    if i.source_type == "resume" and i.source_id:
                        drafts = s.exec(select(Artifact).where(Artifact.user_id == user_id,
                                                                 Artifact.kind == "ResumeDraft")).all()
                        draft = next((item for item in drafts if item.subject.get("resume_id") == i.source_id
                                      and item.body.get("resume_version") == i.source_version), None)
                        if draft:
                            inputs.append({"id": draft.id, "version": draft.version,
                                           "content_hash": draft.content_hash})
                    artifact = save_artifact(s, user_id, "InterviewBrief", {"interview_id": i.id},
                                             projection.model_dump(),
                                             {"agent": "coordinator", "spec_id": "interview.project", "workflow_id": run.id},
                                             inputs=inputs)
                    i.brief_artifact_id = artifact.id
                    s.add(i)
                    s.commit()
                    return artifact, f"{i.mode} 模式；简历 {len(i.resume_text)} 字", \
                        [{"id": artifact.id, "version": artifact.version}]
                execute_step(s, run, "面试视图已生成", project, "岗位 + 简历文本", terminal=False)
                def prepare_questions():
                    inp = build_input(i, j, s)
                    ctx = agent_ctx(user_id, "interview", session=f"interview:{interview_id}")
                    gaps = diagnose(inp, report=report, ctx=ctx)
                    questions = plan_questions(inp, gaps, total=total, report=report, ctx=ctx)
                    qs = [q.model_dump() for q in questions]
                    i.gap_report = gaps.model_dump()
                    i.questions = qs
                    i.state = {"index": 0, "follow_count": 0, "current": qs[0] if qs else None}
                    i.status = "ongoing" if qs else "answered_all"
                    s.add(i)
                    s.flush()
                    return len(qs), f"诊断完成，生成 {len(qs)} 道题", []
                count = execute_step(s, run, "诊断与问题已生成", prepare_questions,
                                     f"InterviewBrief {i.brief_artifact_id}", terminal=False, node_type="agent")
                wait_gate(s, run, "等待面试回答", f"已生成 {count} 道题，等待用户回答")
        except Exception:
            with Session(engine) as s:
                i = s.get(Interview, interview_id)
                i.status = "failed"
                s.add(i)
                s.commit()
            raise
        return {"interview_id": interview_id, "questions": count}

    task = submit(background, session, user.id, "interview:prepare", work)
    return {"interview_id": interview_id, "task_id": task.id}


@router.get("")
def list_interviews(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    rows = session.exec(select(Interview).where(Interview.user_id == user.id)
                        .order_by(Interview.id.desc())).all()
    return [_dict(i, full=False) for i in rows]


@router.get("/{interview_id}")
def get_interview(interview_id: int, user: User = Depends(get_current_user),
                  session: Session = Depends(get_session)):
    return _dict(get_owned(session, Interview, interview_id, user))


@router.post("/{interview_id}/next-round")
def next_round(interview_id: int, background: BackgroundTasks, user: User = Depends(get_current_user),
               session: Session = Depends(get_session)):
    previous = get_owned(session, Interview, interview_id, user)
    if previous.status != "finished":
        raise HTTPException(409, "请先完成本轮面试")
    if previous.source_type not in {"document", "resume", "profile"}:
        raise HTTPException(409, "旧面试缺少可复用的简历来源")
    source = Source(type=previous.source_type, id=previous.source_id,
                    version=None if previous.source_type == "resume" else previous.source_version)
    response = create(CreateBody(job_id=previous.job_id, source=source,
                                 total=max(4, min(len(previous.questions) or 10, 20)), mode=previous.mode),
                      background, user, session)
    current = session.get(Interview, response["interview_id"])
    current.previous_interview_id = previous.id
    current.round = previous.round + 1
    session.add(current)
    session.commit()
    return {**response, "round": current.round}


@router.delete("/{interview_id}")
def delete_interview(interview_id: int, user: User = Depends(get_current_user),
                     session: Session = Depends(get_session)):
    session.delete(get_owned(session, Interview, interview_id, user))
    session.commit()
    return {"ok": True}


@router.post("/{interview_id}/answer")
def answer(interview_id: int, body: AnswerBody, background: BackgroundTasks,
           user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    i = get_owned(session, Interview, interview_id, user)
    if i.status == "finished":
        raise HTTPException(409, "本轮面试报告已生成")
    current = (i.state or {}).get("current")
    if i.status != "ongoing" or not current:
        raise HTTPException(400, "当前没有待回答的问题")
    if (i.state or {}).get("busy"):
        raise HTTPException(409, "上一条回答正在评价中")
    i.state = {**i.state, "busy": True}
    session.add(i)
    session.commit()
    job_id, text, user_id = i.job_id, body.text.strip(), user.id

    def work(report):
        try:
            with Session(engine) as s:
                iv, job = s.get(Interview, interview_id), s.get(Job, job_id)
                inp = build_input(iv, job, s)
                state = dict(iv.state)
            question = Question(**state["current"])
            ev = evaluate_answer(inp, question, text, state.get("follow_count", 0), report=report,
                                 ctx=agent_ctx(user_id, "interview", session=f"interview:{interview_id}"))
        except Exception:
            with Session(engine) as s:
                iv = s.get(Interview, interview_id)
                iv.state = {**iv.state, "busy": False}
                s.add(iv)
                s.commit()
            raise
        with Session(engine) as s:
            iv = s.get(Interview, interview_id)
            state = dict(iv.state)
            turn = {"qid": question.qid, "project": question.project, "level": question.level,
                    "question": question.question, "answer": text or "（未作答）",
                    "is_follow_up": question.is_follow_up, "evaluation": ev.model_dump()}
            iv.turns = [*iv.turns, turn]
            if ev.next_action == "follow_up":
                n = state.get("follow_count", 0) + 1
                base_qid = question.qid.split("-f")[0]
                state["current"] = {"qid": f"{base_qid}-f{n}", "project": question.project,
                                    "level": question.level, "question": ev.follow_up,
                                    "intent": "追问", "anchor": "", "is_follow_up": True}
                state["follow_count"] = n
            else:
                idx = state.get("index", 0) + 1
                state["index"], state["follow_count"] = idx, 0
                state["current"] = iv.questions[idx] if idx < len(iv.questions) else None
                if state["current"] is None:
                    iv.status = "answered_all"
            state["busy"] = False
            iv.state = state
            s.add(iv)
            s.commit()
        return {"evaluation": ev.model_dump(), "next": state["current"]}

    return {"task_id": submit(background, session, user.id, "interview:answer", work).id}


@router.post("/{interview_id}/finish")
def finish(interview_id: int, background: BackgroundTasks, user: User = Depends(get_current_user),
           session: Session = Depends(get_session)):
    i = get_owned(session, Interview, interview_id, user)
    if i.status == "finished":
        raise HTTPException(409, "本轮面试报告已生成")
    if not i.turns:
        raise HTTPException(400, "至少回答一道题后再生成报告")
    job_id, user_id = i.job_id, user.id

    def work(report):
        with Session(engine) as s:
            iv, job = s.get(Interview, interview_id), s.get(Job, job_id)
            inp = build_input(iv, job, s)
            evaluations = [(t.get("project", ""), (t.get("evaluation") or {}).get("scores", {}))
                           for t in iv.turns]
            runs = s.exec(select(WorkflowRun).where(WorkflowRun.user_id == user_id,
                                                   WorkflowRun.kind == "interview")).all()
            run = next((item for item in runs if item.subject.get("interview_id") == interview_id), None)
            if run and run.status == "waiting_user":
                resume_gate(s, run, f"已回答 {len(iv.turns)} 道题")
            if not run:
                run = start(s, user_id, "interview", {"interview_id": interview_id, "job_id": job_id})
            def produce():
                result = final_report(inp, evaluations, report=report,
                                      ctx=agent_ctx(user_id, "interview", session=f"interview:{interview_id}"))
                iv = s.get(Interview, interview_id)
                iv.report = result.model_dump()
                weak_turns = sorted(iv.turns, key=lambda turn: (turn.get("evaluation") or {}).get("scores", {}).get("evidence", 4))
                iv.report["findings"] = [{"req_id": "", "question_id": (weak_turns[index % len(weak_turns)].get("qid", "") if weak_turns else ""),
                                          "gap_type": "interview_feedback", "detail": risk}
                                         for index, risk in enumerate(iv.report.get("risks", [])[:10])]
                iv.status = "finished"
                s.add(iv)
                brief = s.get(Artifact, iv.brief_artifact_id) if iv.brief_artifact_id else None
                inputs = [{"id": brief.id, "version": brief.version, "content_hash": brief.content_hash}] if brief else []
                artifact = save_artifact(s, user_id, "InterviewReport", {"interview_id": interview_id},
                                         iv.report, {"agent": "interview", "spec_id": "interview.report", "workflow_id": run.id},
                                         inputs=inputs)
                return {"report": iv.report}, f"InterviewReport v{artifact.version}，提出 {len(iv.report.get('risks', []))} 项风险", [{"id": artifact.id, "version": artifact.version}]
            report_result = execute_step(s, run, "面试报告已生成", produce,
                                         f"岗位 {job_id} + 本场回答 {len(iv.turns)} 轮",
                                         terminal=False, node_type="agent")
            def feedback():
                iv = s.get(Interview, interview_id)
                proposed = 0
                existing = s.exec(select(MaterialRequest).where(MaterialRequest.user_id == user_id)).all()
                for proposal in propose_requests(iv.report, iv.id, iv.job_id):
                    if any(item.target == proposal["target"] and item.status != "dismissed" for item in existing):
                        continue
                    row = MaterialRequest(user_id=user_id, **proposal)
                    s.add(row)
                    existing.append(row)
                    proposed += 1
                s.flush()
                return {"report": iv.report}, f"提出 {proposed} 条待确认的补充建议", []
            return execute_step(s, run, "补充建议已提出", feedback,
                                f"面试风险 {len(report_result['report'].get('risks', []))} 条")

    return {"task_id": submit(background, session, user.id, "interview:report", work).id}


@router.post("/{interview_id}/findings/{finding_id}/request")
def request_from_finding(interview_id: int, finding_id: int, user: User = Depends(get_current_user),
                         session: Session = Depends(get_session)):
    interview = get_owned(session, Interview, interview_id, user)
    findings = (interview.report or {}).get("findings") or []
    if finding_id < 0 or finding_id >= len(findings):
        raise HTTPException(404, "面试发现不存在")
    target = {"job_id": interview.job_id, "interview_id": interview.id, "finding": finding_id}
    existing = session.exec(select(MaterialRequest).where(MaterialRequest.user_id == user.id)).all()
    row = next((item for item in existing if item.target == target and item.status != "dismissed"), None)
    if row:
        return row
    finding = findings[finding_id]
    row = MaterialRequest(user_id=user.id, target=target, gap_type=finding.get("gap_type", "interview_feedback"),
                          question=f"关于“{finding.get('detail', '')}”，你是否有真实经历或材料可以补充？",
                          origin={"interview_id": interview.id, "question_id": finding.get("question_id", "")},
                          status="proposed")
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
