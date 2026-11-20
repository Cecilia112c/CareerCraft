"""CareerCraft API.  Run from the CareerCraft/ folder:

    python -m uvicorn backend.app.main:app --reload --port 8000
"""

import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from backend.app.config import ROOT
from backend.app.db import engine, init_db
from sqlmodel import Session, select
from backend.app.models import User, WorkflowRun, WorkflowStep
from backend.app.workflows.engine import recover_interrupted
from backend.app.routers import (
    auth, clip, evidence, insights, interviews, jobs, knowledge, material_requests, memory, profile, resumes, tasks, today, workflows,
)
from backend.app.scheduler import start_scheduler, stop_scheduler
from backend.app.services.agent_runtime import init_agent_runtime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _restart_interrupted_job(run_id: str, step_id: str, user_id: int) -> None:
    with Session(engine) as session:
        owner = session.get(User, user_id)
        if owner:
            try:
                workflows.retry_step(run_id, step_id, BackgroundTasks(), owner, session)
            except Exception:
                logging.getLogger(__name__).exception("Cannot resume job workflow %s", run_id)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with Session(engine) as session:
        recover_interrupted(session, older_than_seconds=0)
    init_agent_runtime()          # harness：记忆库 backend/data/agent_memory.db + 模型提供方
    restart_tasks = BackgroundTasks()
    restart_jobs: list[tuple[str, str, int]] = []
    with Session(engine) as session:
        interrupted = session.exec(select(WorkflowStep).where(WorkflowStep.status == "pending")).all()
        for step in interrupted:
            if "执行中断" not in step.error:
                continue
            run = session.get(WorkflowRun, step.run_id)
            if not run or run.status != "failed":
                continue
            if run.kind == "job_import":
                restart_jobs.append((run.id, step.id, run.user_id))
                continue
            if run.kind not in {"resume_generate", "knowledge_ingest", "interview"}:
                continue
            owner = session.get(User, run.user_id)
            if owner:
                try:
                    workflows.retry_step(run.id, step.id, restart_tasks, owner, session)
                except Exception:
                    logging.getLogger(__name__).exception("Cannot resume workflow %s", run.id)
    if restart_tasks.tasks:
        asyncio.create_task(restart_tasks())
    for run_id, step_id, user_id in restart_jobs:
        asyncio.create_task(asyncio.to_thread(_restart_interrupted_job, run_id, step_id, user_id))
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="CareerCraft", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"], allow_credentials=True,
)


@app.exception_handler(ValidationError)
async def pydantic_error(_request: Request, exc: ValidationError):
    return JSONResponse(status_code=422, content={"detail": f"数据格式错误：{exc.errors()[:3]}"})


for module in (auth, profile, jobs, knowledge, material_requests, evidence, clip, today, insights, resumes, interviews, memory, tasks, workflows):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"ok": True}


# 生产/演示：先 `npm run build`，再由后端直接托管前端（单端口）
class SPAStaticFiles(StaticFiles):
    """Serve index.html for client-side routes such as /resumes/3."""

    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except Exception:  # noqa: BLE001  (starlette raises HTTPException 404)
            response = None
        if response is None or response.status_code == 404:
            return await super().get_response("index.html", scope)
        return response


_dist = ROOT / "frontend" / "dist"
if _dist.exists():
    app.mount("/", SPAStaticFiles(directory=_dist, html=True), name="frontend")
