"""Read-only workflow timeline and artifact provenance."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from backend.app.auth import get_current_user
from backend.app.db import engine, get_session
from backend.app.models import Artifact, Job, User, WorkflowRun, WorkflowStep
from backend.app.services.jobs import job_posting
from agents.jd_agent.brief import build_brief
from backend.app.workflows.artifacts import save_artifact
import hashlib
from backend.app.services.agent_runtime import memory
from backend.app.workflows.engine import resume_gate
from backend.app.services.tasks import submit

router = APIRouter(prefix="/api", tags=["workflows"])


@router.get("/jobs/{job_id}/brief")
def job_brief(job_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    job = session.exec(select(Job).where(Job.id == job_id, Job.user_id == user.id)).first()
    if not job or not job.brief_artifact_id:
        raise HTTPException(404, "岗位交接产物不存在")
    return session.get(Artifact, job.brief_artifact_id)


@router.get("/artifacts/{artifact_id}")
def artifact_detail(artifact_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    row = session.exec(select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user.id)).first()
    if not row:
        raise HTTPException(404, "产物不存在")
    candidates = session.exec(select(Artifact).where(Artifact.user_id == user.id)).all()
    downstream = [{"id": item.id, "kind": item.kind, "version": item.version, "status": item.status}
                  for item in candidates if any(ref.get("id") == row.id for ref in item.inputs)]
    return {"artifact": row, "downstream": downstream}


@router.get("/workflows")
def workflows(subject: str = "", user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    rows = session.exec(select(WorkflowRun).where(WorkflowRun.user_id == user.id).order_by(WorkflowRun.started_at.desc()).limit(100)).all()
    return [row for row in rows if not subject or f"{next(iter(row.subject), '')}:{next(iter(row.subject.values()), '')}" == subject]


@router.get("/workflows/{run_id}")
def workflow_detail(run_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    row = session.exec(select(WorkflowRun).where(WorkflowRun.id == run_id, WorkflowRun.user_id == user.id)).first()
    if not row:
        raise HTTPException(404, "工作流不存在")
    steps = session.exec(select(WorkflowStep).where(WorkflowStep.run_id == row.id).order_by(WorkflowStep.ordinal)).all()
    return {"run": row, "steps": steps}


@router.get("/workflows/{run_id}/steps/{step_id}")
def workflow_step_detail(run_id: str, step_id: str, user: User = Depends(get_current_user),
                         session: Session = Depends(get_session)):
    run = session.exec(select(WorkflowRun).where(WorkflowRun.id == run_id,
                                                WorkflowRun.user_id == user.id)).first()
    step = session.exec(select(WorkflowStep).where(WorkflowStep.id == step_id,
                                                  WorkflowStep.run_id == run_id)).first()
    if not run or not step:
        raise HTTPException(404, "工作流步骤不存在")
    runs = memory().store.list_runs(str(user.id), limit=100)
    linked = [{key: item.get(key) for key in ("run_id", "agent", "spec_id", "status", "model", "iterations",
                                               "repairs", "tool_calls", "latency_ms", "tokens") if key in item}
              for item in runs if item.get("workflow_step_id") == step.id]
    return {"step": step, "agent_runs": linked}


@router.post("/workflows/{run_id}/resume")
def resume_workflow(run_id: str, background: BackgroundTasks, user: User = Depends(get_current_user),
                    session: Session = Depends(get_session)):
    run = session.exec(select(WorkflowRun).where(WorkflowRun.id == run_id,
                                                 WorkflowRun.user_id == user.id)).first()
    if not run:
        raise HTTPException(404, "工作流不存在")
    if run.kind != "resume_generate" or run.status != "waiting_user":
        raise HTTPException(409, "此工作流无法从等待节点继续")
    resume_id = run.subject.get("resume_id")
    from backend.app.models import Resume
    from backend.app.routers.resumes import _generate_in_workflow
    resume = session.exec(select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)).first()
    if not resume:
        raise HTTPException(404, "简历不存在")
    resume_gate(session, run, "用户决定继续生成")
    user_id = user.id
    def work(report):
        with Session(engine) as s:
            return _generate_in_workflow(s, s.get(WorkflowRun, run_id), resume_id, user_id, report)
    task = submit(background, session, user.id, "resume:generate", work)
    return {"resume_id": resume_id, "task_id": task.id}


@router.post("/workflows/{run_id}/steps/{step_id}/retry")
def retry_step(run_id: str, step_id: str, background: BackgroundTasks, user: User = Depends(get_current_user),
               session: Session = Depends(get_session)):
    run = session.exec(select(WorkflowRun).where(WorkflowRun.id == run_id,
                                                 WorkflowRun.user_id == user.id)).first()
    step = session.exec(select(WorkflowStep).where(WorkflowStep.id == step_id,
                                                   WorkflowStep.run_id == run_id)).first()
    if not run or not step:
        raise HTTPException(404, "工作流步骤不存在")
    if step.status not in {"failed", "pending"} or run.status != "failed":
        raise HTTPException(409, "此步骤暂不支持重试")
    ordered = session.exec(select(WorkflowStep).where(WorkflowStep.run_id == run_id)
                           .order_by(WorkflowStep.ordinal)).all()
    unfinished = next((item for item in ordered if item.status not in {"done", "skipped"}), None)
    if unfinished is None or unfinished.id != step.id:
        raise HTTPException(409, "请先重试前一个未完成的步骤")
    if step.status == "pending" and not step.error:
        raise HTTPException(409, "此步骤尚未开始，不能越过前置步骤")
    if run.kind == "resume_generate" and step.name in {"依据已匹配", "定向简历已生成"}:
        from backend.app.models import Resume
        from backend.app.routers.resumes import _generate_in_workflow, _retry_match_in_workflow
        resume_id = run.subject.get("resume_id")
        resume = session.exec(select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)).first()
        if not resume:
            raise HTTPException(404, "简历不存在")
        step.status, step.error = "pending", ""
        run.status, run.finished_at = "running", None
        session.add(step)
        session.add(run)
        session.commit()
        user_id = user.id
        def work(report):
            with Session(engine) as s:
                fn = _retry_match_in_workflow if step.name == "依据已匹配" else _generate_in_workflow
                return fn(s, s.get(WorkflowRun, run_id), resume_id, user_id, report)
        task = submit(background, session, user.id, "resume:retry", work)
        return {"run": run, "step": step, "task_id": task.id}
    if run.kind == "knowledge_ingest" and step.name == "事实已抽取":
        from backend.app.routers.knowledge import _queue_extraction
        source_id = run.subject.get("source_id")
        step.status, step.error = "pending", ""
        run.status, run.finished_at = "running", None
        session.add(step)
        session.add(run)
        session.commit()
        task_id = _queue_extraction(background, session, user.id, source_id, run_id)
        return {"run": run, "step": step, "task_id": task_id}
    if run.kind == "interview":
        from backend.app.models import Interview, MaterialRequest
        from backend.app.routers.interviews import _prepare_questions_step, _project_brief_step, finish
        from agents.feedback.extract import propose_requests
        from backend.app.workflows.engine import execute_step
        interview_id = run.subject.get("interview_id")
        interview = session.exec(select(Interview).where(Interview.id == interview_id,
                                                         Interview.user_id == user.id)).first()
        if not interview:
            raise HTTPException(404, "面试不存在")
        if step.name not in {"面试视图已生成", "诊断与问题已生成", "面试报告已生成", "补充建议已提出"}:
            raise HTTPException(409, "此步骤暂不支持重试")
        step.status, step.error = "pending", ""
        run.status, run.finished_at = "running", None
        session.add(step)
        session.add(run)
        session.commit()
        if step.name == "面试报告已生成":
            return finish(interview_id, background, user, session)
        user_id = user.id
        if step.name in {"面试视图已生成", "诊断与问题已生成"}:
            def work(report):
                with Session(engine) as s:
                    active = s.get(WorkflowRun, run_id)
                    if step.name == "面试视图已生成":
                        _project_brief_step(s, active, interview_id, user_id)
                    count = _prepare_questions_step(s, active, interview_id, user_id,
                                                    int(run.subject.get("question_total") or 10), report)
                    return {"interview_id": interview_id, "questions": count}
            task = submit(background, session, user_id, "interview:retry", work)
            return {"run": run, "step": step, "task_id": task.id}
        if step.name == "补充建议已提出":
            def feedback():
                existing = session.exec(select(MaterialRequest).where(MaterialRequest.user_id == user_id)).all()
                proposed = 0
                for item in propose_requests(interview.report, interview.id, interview.job_id):
                    if any(row.target == item["target"] and row.status != "dismissed" for row in existing):
                        continue
                    row = MaterialRequest(user_id=user_id, **item)
                    session.add(row)
                    existing.append(row)
                    proposed += 1
                session.flush()
                return {"report": interview.report}, f"提出 {proposed} 条待确认的补充建议", []
            execute_step(session, run, step.name, feedback, "面试报告反馈", node_type="code")
            return {"run": run, "step": step}
    if run.kind != "job_import" or step.name != "JD 已解析":
        raise HTTPException(409, "此步骤暂不支持重试")
    job = session.exec(select(Job).where(Job.id == run.subject.get("job_id"), Job.user_id == user.id)).first()
    raw = run.subject.get("source_text", "")
    if not job and not raw:
        raise HTTPException(404, "职位原文不存在，无法重试")
    step.status, step.error = "pending", ""
    run.status, run.finished_at = "running", None
    session.add(step)
    session.add(run)
    session.commit()
    def produce():
        from agents.jd_agent import normalize_text
        from backend.app.services.jobs import goal_from_setting, get_push_setting, load_profile, save_jobs
        from backend.app.services.agent_runtime import agent_ctx
        if job:
            posting = job_posting(job)
            source_text = raw or "\n".join([posting.summary, *posting.responsibilities, *posting.requirements])
            row = job
        else:
            posting = normalize_text(raw, url=run.subject.get("source_url", ""),
                                     profile=load_profile(session, user.id),
                                     goal=goal_from_setting(get_push_setting(session, user.id)),
                                     ctx=agent_ctx(user.id, "jd"))
            saved, _ = save_jobs(session, user.id, [posting])
            row = session.get(Job, saved[0])
            row.raw_sha256 = hashlib.sha256(raw.strip().encode()).hexdigest()
            source_text = raw
        brief = build_brief(posting, source_text)
        artifact = save_artifact(session, user.id, "JobBrief", {"job_id": row.id}, brief,
                                 {"agent": "jd", "spec_id": "jd.normalize", "workflow_id": run.id})
        row.brief_artifact_id = artifact.id
        run.subject = {"job_id": row.id}
        session.add(row)
        session.add(run)
        session.commit()
        return row.id, f"JobBrief v{artifact.version}，{len(brief['requirements'])} 条要求", \
            [{"id": artifact.id, "version": artifact.version}]
    from backend.app.workflows.engine import execute_step
    job_id = execute_step(session, run, step.name, produce, "重试 JD 解析", terminal=True, node_type="agent")
    return {"run": run, "step": step, "job_id": job_id}
