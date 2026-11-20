"""Versioned handoff artifacts with content hashes and dependency invalidation."""

import hashlib
import json
import uuid

from sqlmodel import Session, select

from backend.app.models import Artifact
from agents.contracts import JobBrief, ResumeEvidence
from agents.contracts.interview import InterviewBrief, InterviewReport
from agents.contracts.requests import ProfileUpdateProposal

BODY_TYPES = {"JobBrief": JobBrief, "ResumeEvidence": ResumeEvidence,
              "InterviewBrief": InterviewBrief, "InterviewReport": InterviewReport,
              "ProfileUpdateProposal": ProfileUpdateProposal}


def save_artifact(session: Session, user_id: int, kind: str, subject: dict, body: dict,
                  produced_by: dict, inputs: list[dict] | None = None, sources: list[dict] | None = None) -> Artifact:
    contract = BODY_TYPES.get(kind)
    if contract:
        body = contract.model_validate(body).model_dump(mode="json")
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, default=str).encode()
    content_hash = hashlib.sha256(encoded).hexdigest()
    rows = session.exec(select(Artifact).where(Artifact.user_id == user_id, Artifact.kind == kind)).all()
    previous = [row for row in rows if row.subject == subject]
    version = max((row.version for row in previous), default=0) + 1
    for row in previous:
        if row.status == "active":
            row.status = "superseded"
            session.add(row)
            invalidate_dependents(session, user_id, row.id)
    artifact = Artifact(id="art_" + uuid.uuid4().hex, user_id=user_id, kind=kind, version=version,
                        subject=subject, body=body, produced_by=produced_by, inputs=inputs or [],
                        sources=sources or [], content_hash=content_hash)
    session.add(artifact)
    session.commit()
    session.refresh(artifact)
    return artifact


def invalidate_dependents(session: Session, user_id: int, artifact_id: str) -> None:
    rows = session.exec(select(Artifact).where(Artifact.user_id == user_id)).all()
    pending = [artifact_id]
    seen = set()
    while pending:
        upstream = pending.pop()
        if upstream in seen:
            continue
        seen.add(upstream)
        for row in rows:
            if row.status == "active" and any(ref.get("id") == upstream for ref in row.inputs):
                row.status = "stale"
                session.add(row)
                pending.append(row.id)
    session.flush()


def invalidate_evidence_for_user(session: Session, user_id: int) -> None:
    """A confirmed fact changed; all requirement matches may need recalculation."""
    rows = session.exec(select(Artifact).where(Artifact.user_id == user_id, Artifact.kind == "ResumeEvidence",
                                               Artifact.status == "active")).all()
    for row in rows:
        row.status = "stale"
        session.add(row)
        invalidate_dependents(session, user_id, row.id)
    drafts = session.exec(select(Artifact).where(Artifact.user_id == user_id, Artifact.kind == "ResumeDraft",
                                                 Artifact.status == "active")).all()
    for row in drafts:
        row.status = "stale"
        session.add(row)
        invalidate_dependents(session, user_id, row.id)
    session.flush()
