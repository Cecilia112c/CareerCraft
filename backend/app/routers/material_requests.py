"""User-reviewed requests for missing evidence."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from backend.app.auth import get_current_user
from backend.app.db import get_session
from backend.app.models import EvidenceClaim, KnowledgeSource, MaterialRequest, User
from backend.app.workflows.artifacts import invalidate_evidence_for_user

router = APIRouter(prefix="/api/material-requests", tags=["material-requests"])


class AnswerBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    project_id: str = ""


class AttachBody(BaseModel):
    source_id: int


def owned(session: Session, user_id: int, request_id: int) -> MaterialRequest:
    row = session.exec(select(MaterialRequest).where(MaterialRequest.id == request_id,
                                                     MaterialRequest.user_id == user_id)).first()
    if not row:
        raise HTTPException(404, "补充建议不存在")
    return row


@router.get("")
def list_requests(status: str = "open", user: User = Depends(get_current_user),
                  session: Session = Depends(get_session)):
    return session.exec(select(MaterialRequest).where(MaterialRequest.user_id == user.id,
                                                     MaterialRequest.status == status)
                        .order_by(MaterialRequest.created_at.desc())).all()


@router.post("/{request_id}/confirm")
def confirm_request(request_id: int, user: User = Depends(get_current_user),
                    session: Session = Depends(get_session)):
    row = owned(session, user.id, request_id)
    if row.status != "proposed":
        raise HTTPException(409, "只有待确认建议可以确认")
    row.status = "open"
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    return row


@router.post("/{request_id}/answer")
def answer_request(request_id: int, body: AnswerBody, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)):
    row = owned(session, user.id, request_id)
    if row.status != "open":
        raise HTTPException(409, "请先确认补充建议")
    project_id = body.project_id or row.target.get("project_id", "")
    if project_id:
        from agents.core.schemas import iter_projects
        from backend.app.services.jobs import load_profile
        valid = {project.id for project, _ in iter_projects(load_profile(session, user.id))}
        if project_id not in valid:
            raise HTTPException(422, "项目不存在")
    claim = EvidenceClaim(user_id=user.id, statement=body.text.strip(), status="confirmed", level="L1",
                          origin="user_answer", confidence=1.0, project_id=project_id,
                          confirmed_at=datetime.now(timezone.utc))
    session.add(claim)
    session.flush()
    row.status = "resolved"
    row.resolution = {"claim_id": claim.id}
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    invalidate_evidence_for_user(session, user.id)
    session.commit()
    return {"request": row, "claim": claim}


@router.post("/{request_id}/attach")
def attach_source(request_id: int, body: AttachBody, user: User = Depends(get_current_user),
                  session: Session = Depends(get_session)):
    row = owned(session, user.id, request_id)
    if row.status != "open":
        raise HTTPException(409, "只有待补充的建议可以关联材料")
    source = session.exec(select(KnowledgeSource).where(KnowledgeSource.id == body.source_id,
                                                        KnowledgeSource.user_id == user.id)).first()
    if not source:
        raise HTTPException(404, "材料不存在")
    row.status = "resolved"
    row.resolution = {"source_id": source.id, "requires_fact_confirmation": True}
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    return row


@router.post("/{request_id}/dismiss")
def dismiss_request(request_id: int, user: User = Depends(get_current_user),
                    session: Session = Depends(get_session)):
    row = owned(session, user.id, request_id)
    row.status = "dismissed"
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    return row
