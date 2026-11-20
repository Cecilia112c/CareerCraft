from pathlib import Path
import shutil

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from backend.app.auth import check_password, get_current_user, hash_password, make_token
from backend.app.db import get_session
from backend.app.config import UPLOAD_DIR
from backend.app.models import (Artifact, Document, EvidenceClaim, InsightSnapshot, Interview, Job,
                                KnowledgeChunk, KnowledgeSource, MaterialRequest, Profile, PushSetting,
                                Resume, ResumePatchFeedback, ResumeVersion, Task, Todo, User, WorkflowRun,
                                WorkflowStep)
from backend.app.services.agent_runtime import memory

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_\-.@一-龥]+$")
    password: str = Field(min_length=6, max_length=64)


class DeleteAccountBody(BaseModel):
    password: str


def _user_dict(user: User) -> dict:
    return {"id": user.id, "username": user.username}


@router.post("/register")
def register(body: Credentials, session: Session = Depends(get_session)):
    if session.exec(select(User).where(User.username == body.username)).first():
        raise HTTPException(400, "用户名已被注册")
    user = User(username=body.username, password_hash=hash_password(body.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    session.add(Profile(user_id=user.id, data={}))
    session.commit()
    return {"token": make_token(user.id), "user": _user_dict(user)}


@router.post("/login")
def login(body: Credentials, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == body.username)).first()
    if user is None or not check_password(body.password, user.password_hash):
        raise HTTPException(400, "用户名或密码错误")
    return {"token": make_token(user.id), "user": _user_dict(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_dict(user)


@router.delete("/me")
def delete_account(body: DeleteAccountBody, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)):
    if not check_password(body.password, user.password_hash):
        raise HTTPException(400, "密码不正确")
    resume_ids = [row.id for row in session.exec(select(Resume).where(Resume.user_id == user.id)).all()]
    workflow_ids = [row.id for row in session.exec(select(WorkflowRun).where(WorkflowRun.user_id == user.id)).all()]
    source_ids = [row.id for row in session.exec(select(KnowledgeSource).where(KnowledgeSource.user_id == user.id)).all()]
    for model, column, keys in (
        (WorkflowStep, WorkflowStep.run_id, workflow_ids),
        (ResumeVersion, ResumeVersion.resume_id, resume_ids),
        (KnowledgeChunk, KnowledgeChunk.source_id, source_ids),
    ):
        if keys:
            for row in session.exec(select(model).where(column.in_(keys))).all():
                session.delete(row)
    for model in (Artifact, EvidenceClaim, MaterialRequest, ResumePatchFeedback, Task, Interview,
                  Todo, InsightSnapshot, PushSetting, KnowledgeSource, Document, Resume, Job, Profile, WorkflowRun):
        for row in session.exec(select(model).where(model.user_id == user.id)).all():
            session.delete(row)
    session.delete(user)
    session.commit()
    memory().store.delete_user_data(str(user.id))
    root = UPLOAD_DIR.resolve()
    user_folder = (UPLOAD_DIR / str(user.id)).resolve()
    if user_folder.parent == root and user_folder.exists():
        shutil.rmtree(user_folder)
    return {"ok": True}
