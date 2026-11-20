from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from agents.core.schemas import ProfileData
from agents.parser_agent import parse_pdf
from agents.parser_agent.layout import extract_lines
from backend.app.auth import get_current_user, get_owned
from backend.app.config import MAX_UPLOAD_MB, UPLOAD_DIR
from backend.app.db import get_session
from backend.app.models import Document, Profile, User
from backend.app.services.resume_ops import save_profile
from backend.app.services.agent_runtime import agent_ctx
from backend.app.services.tasks import submit
from backend.app.workflows.artifacts import invalidate_evidence_for_user

router = APIRouter(prefix="/api", tags=["profile"])


class ProfileBody(BaseModel):
    data: dict


class ParseBody(BaseModel):
    mode: str = "rule"   # rule | llm


@router.get("/profile")
def get_profile(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    row = session.exec(select(Profile).where(Profile.user_id == user.id)).first()
    data = ProfileData.model_validate(row.data if row else {})
    return {"data": data.model_dump(mode="json"),
            "updated_at": row.updated_at.isoformat() if row else None}


@router.put("/profile")
def put_profile(body: ProfileBody, user: User = Depends(get_current_user),
                session: Session = Depends(get_session)):
    data = ProfileData.model_validate(body.data)
    row = save_profile(session, user.id, data)
    invalidate_evidence_for_user(session, user.id)
    session.commit()
    return {"data": data.model_dump(mode="json"), "updated_at": row.updated_at.isoformat()}


# ---------------------------------------------------------------- documents

@router.post("/documents")
async def upload_document(file: UploadFile = File(...), user: User = Depends(get_current_user),
                          session: Session = Depends(get_session)):
    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"文件不能超过 {MAX_UPLOAD_MB}MB")
    if not content.startswith(b"%PDF"):
        raise HTTPException(400, "只支持 PDF 文件")
    try:
        text = "\n".join(line.text for line in extract_lines(content))
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "PDF 无法解析，可能已损坏或加密")
    folder = UPLOAD_DIR / str(user.id)
    folder.mkdir(parents=True, exist_ok=True)
    doc = Document(user_id=user.id, filename=(file.filename or "resume.pdf")[:120], path="", text=text)
    session.add(doc)
    session.commit()
    session.refresh(doc)
    path = folder / f"{doc.id}.pdf"
    path.write_bytes(content)
    doc.path = str(path)
    session.add(doc)
    session.commit()
    return {"id": doc.id, "filename": doc.filename, "has_text": bool(text.strip()),
            "created_at": doc.created_at.isoformat()}


@router.get("/documents")
def list_documents(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    rows = session.exec(select(Document).where(Document.user_id == user.id)
                        .order_by(Document.id.desc())).all()
    return [{"id": d.id, "filename": d.filename, "created_at": d.created_at.isoformat(),
             "has_text": bool(d.text.strip())} for d in rows]


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, user: User = Depends(get_current_user),
                    session: Session = Depends(get_session)):
    doc = get_owned(session, Document, doc_id, user)
    try:
        from pathlib import Path
        Path(doc.path).unlink(missing_ok=True)
    except OSError:
        pass
    session.delete(doc)
    session.commit()
    return {"ok": True}


@router.post("/documents/{doc_id}/parse")
def parse_document(doc_id: int, body: ParseBody, background: BackgroundTasks,
                   user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    doc = get_owned(session, Document, doc_id, user)
    path, mode, user_id = doc.path, ("llm" if body.mode == "llm" else "rule"), user.id

    def work(report):
        with open(path, "rb") as fh:
            result = parse_pdf(fh.read(), mode=mode, report=report, ctx=agent_ctx(user_id, "parser"))
        data = result.model_dump(mode="json")
        data.pop("text", None)
        return data

    task = submit(background, session, user.id, f"parse:{mode}", work)
    return {"task_id": task.id}
