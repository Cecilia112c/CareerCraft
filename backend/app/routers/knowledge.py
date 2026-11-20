"""Minimal user-owned knowledge library with explicit fact confirmation."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from backend.app.auth import get_current_user
from backend.app.db import engine, get_session
from backend.app.config import UPLOAD_DIR
from backend.app.knowledge.safety import chunk_text, read_zip_text, redact
from backend.app.knowledge.retrieval import search_chunks
from backend.app.knowledge.repo_profile import profile_from_text
from backend.app.knowledge.github import public_repo_overview, repository_parts
from backend.app.models import EvidenceClaim, KnowledgeChunk, KnowledgeSource, User, WorkflowRun
from backend.app.workflows.artifacts import invalidate_evidence_for_user
from backend.app.workflows.engine import execute_step, resume_gate, skip_gate, start, wait_gate
from backend.app.services.agent_runtime import agent_ctx
from backend.app.services.tasks import submit
from agents.harness import invoke
from agents.knowledge_agent.specs import EXTRACT

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
MAX_USER_BYTES = 500 * 1024 * 1024


class NoteBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=100000)


class ConfirmBody(BaseModel):
    statement: str | None = Field(default=None, max_length=2000)
    project_id: str = ""


class GitHubBody(BaseModel):
    url: str
    token: str = ""


class SourcePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    linked_project_ids: list[str] | None = None


class BatchClaims(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=100)
    action: str


@router.post("/sources/certificate")
async def add_certificate(name: str = Form(...), issuer: str = Form(...), issued_at: str = Form(""),
                          file: UploadFile = File(...), user: User = Depends(get_current_user),
                          session: Session = Depends(get_session)):
    extension = (file.filename or "").rsplit(".", 1)[-1].lower()
    if extension not in {"pdf", "png", "jpg", "jpeg"}:
        raise HTTPException(400, "证书仅支持 PDF、PNG、JPG")
    data = await file.read(20 * 1024 * 1024 + 1)
    if not data or len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "证书文件需在 20MB 以内")
    used = sum(row.size for row in session.exec(select(KnowledgeSource).where(KnowledgeSource.user_id == user.id)).all())
    if used + len(data) > MAX_USER_BYTES:
        raise HTTPException(400, "资料库空间不足")
    if extension == "pdf" and not data.startswith(b"%PDF"):
        raise HTTPException(400, "PDF 文件无效")
    if extension == "png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(400, "PNG 文件无效")
    if extension in {"jpg", "jpeg"} and not data.startswith(b"\xff\xd8"):
        raise HTTPException(400, "JPG 文件无效")
    statement = f"{name[:120]}｜颁发机构：{issuer[:120]}" + (f"｜日期：{issued_at[:40]}" if issued_at else "")
    source = KnowledgeSource(user_id=user.id, kind="certificate", title=name[:120],
                             filename=(file.filename or "certificate")[:120], size=len(data),
                             sha256=hashlib.sha256(data).hexdigest(), meta={"issuer": issuer[:120], "issued_at": issued_at[:40]})
    session.add(source)
    session.flush()
    folder = UPLOAD_DIR / str(user.id) / "knowledge"
    folder.mkdir(parents=True, exist_ok=True)
    saved_path = folder / f"{source.id}.{extension}"
    saved_path.write_bytes(data)
    source.path = str(saved_path)
    chunk = KnowledgeChunk(source_id=source.id, user_id=user.id, ord=0, text=statement)
    session.add(chunk)
    session.flush()
    session.add(EvidenceClaim(user_id=user.id, statement=statement, claim_type="certificate",
                              source_chunk_ids=[chunk.id], source_quote=statement, status="proposed", level="L2",
                              origin="certificate", confidence=1.0))
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


@router.post("/sources/github")
def add_github(body: GitHubBody, background: BackgroundTasks, user: User = Depends(get_current_user),
               session: Session = Depends(get_session)):
    try:
        owner, repo = repository_parts(body.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    source = KnowledgeSource(user_id=user.id, kind="github", title=f"{owner}/{repo}",
                             status="pending", meta={"url": f"https://github.com/{owner}/{repo}"})
    session.add(source)
    session.commit()
    session.refresh(source)
    return {"source": source, "task_id": _queue_extraction(background, session, user.id, source.id,
                                                               github_token=body.token)}


@router.post("/sources")
async def upload_source(background: BackgroundTasks, file: UploadFile = File(...), user: User = Depends(get_current_user),
                        session: Session = Depends(get_session)):
    name = (file.filename or "material")[:120]
    ext = name.rsplit(".", 1)[-1].lower()
    if ext not in {"pdf", "docx", "md", "txt", "zip"}:
        raise HTTPException(400, "不支持的文件类型")
    data = await file.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "文件不能超过 20MB")
    used = sum(row.size for row in session.exec(select(KnowledgeSource).where(KnowledgeSource.user_id == user.id)).all())
    if used + len(data) > MAX_USER_BYTES:
        raise HTTPException(400, "资料库空间不足，请删除旧材料后重试")
    source = KnowledgeSource(user_id=user.id, kind="repo_zip" if ext == "zip" else "document",
                             title=name, filename=name, size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                             status="pending")
    session.add(source)
    session.flush()
    folder = UPLOAD_DIR / str(user.id) / "knowledge"
    folder.mkdir(parents=True, exist_ok=True)
    saved_path = folder / f"{source.id}.{ext}"
    saved_path.write_bytes(data)
    source.path = str(saved_path)
    session.add(source)
    session.commit()
    session.refresh(source)
    return {"source": source, "task_id": _queue_extraction(background, session, user.id, source.id)}


@router.post("/sources/note")
def add_note(body: NoteBody, background: BackgroundTasks, user: User = Depends(get_current_user),
             session: Session = Depends(get_session)):
    cleaned, count = redact(body.text)
    source = KnowledgeSource(user_id=user.id, kind="note", title=body.title,
                             size=len(body.text.encode()), sha256=hashlib.sha256(body.text.encode()).hexdigest(),
                             meta={"redacted_count": count})
    session.add(source)
    session.flush()
    for i, part in enumerate(chunk_text(cleaned)):
        session.add(KnowledgeChunk(source_id=source.id, user_id=user.id, ord=i, text=part))
    session.commit()
    session.refresh(source)
    return {"source": source, "task_id": _queue_extraction(background, session, user.id, source.id)}


@router.get("/sources")
def list_sources(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    sources = session.exec(select(KnowledgeSource).where(KnowledgeSource.user_id == user.id)
                           .order_by(KnowledgeSource.created_at.desc())).all()
    chunks = session.exec(select(KnowledgeChunk).where(KnowledgeChunk.user_id == user.id)).all()
    claims = session.exec(select(EvidenceClaim).where(EvidenceClaim.user_id == user.id)).all()
    chunk_sources = {chunk.id: chunk.source_id for chunk in chunks}
    chunk_counts = {source.id: 0 for source in sources}
    claim_counts = {source.id: 0 for source in sources}
    for chunk in chunks:
        chunk_counts[chunk.source_id] = chunk_counts.get(chunk.source_id, 0) + 1
    for claim in claims:
        for source_id in {chunk_sources.get(chunk_id) for chunk_id in claim.source_chunk_ids} - {None}:
            claim_counts[source_id] = claim_counts.get(source_id, 0) + 1
    return [{**source.model_dump(), "chunk_count": chunk_counts[source.id],
             "claim_count": claim_counts[source.id]} for source in sources]


@router.get("/sources/{source_id}")
def source_detail(source_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    source = session.exec(select(KnowledgeSource).where(KnowledgeSource.id == source_id,
                                                        KnowledgeSource.user_id == user.id)).first()
    if not source:
        raise HTTPException(404, "材料不存在")
    chunks = session.exec(select(KnowledgeChunk).where(KnowledgeChunk.source_id == source_id,
                                                       KnowledgeChunk.user_id == user.id).order_by(KnowledgeChunk.ord)).all()
    chunk_ids = {chunk.id for chunk in chunks}
    claims = session.exec(select(EvidenceClaim).where(EvidenceClaim.user_id == user.id)).all()
    return {"source": source, "chunks": chunks,
            "claims": [claim for claim in claims if chunk_ids.intersection(claim.source_chunk_ids)]}


@router.patch("/sources/{source_id}")
def update_source(source_id: int, body: SourcePatch, user: User = Depends(get_current_user),
                  session: Session = Depends(get_session)):
    source = session.exec(select(KnowledgeSource).where(KnowledgeSource.id == source_id,
                                                        KnowledgeSource.user_id == user.id)).first()
    if not source:
        raise HTTPException(404, "材料不存在")
    if body.linked_project_ids is not None:
        from agents.core.schemas import iter_projects
        from backend.app.services.jobs import load_profile
        valid = {project.id for project, _ in iter_projects(load_profile(session, user.id))}
        if len(body.linked_project_ids) > 30 or not set(body.linked_project_ids) <= valid:
            raise HTTPException(422, "关联项目无效")
        source.linked_project_ids = list(dict.fromkeys(body.linked_project_ids))
        if len(source.linked_project_ids) == 1:
            chunk_ids = {chunk.id for chunk in session.exec(select(KnowledgeChunk).where(
                KnowledgeChunk.source_id == source_id, KnowledgeChunk.user_id == user.id)).all()}
            for claim in session.exec(select(EvidenceClaim).where(EvidenceClaim.user_id == user.id,
                                                                  EvidenceClaim.status == "proposed")).all():
                if chunk_ids.intersection(claim.source_chunk_ids):
                    claim.project_id = source.linked_project_ids[0]
                    session.add(claim)
    if body.title is not None:
        source.title = body.title.strip()
    session.add(source)
    session.commit()
    return source


def _parse_uploaded_material(data: bytes, ext: str) -> str:
    if ext == "pdf":
        import fitz
        with fitz.open(stream=data, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc)
    if ext == "docx":
        import io
        import zipfile
        from xml.etree import ElementTree
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if archive.getinfo("word/document.xml").file_size > 5 * 1024 * 1024:
                raise ValueError("DOCX 正文超过 5MB")
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        return "\n".join("".join(node.text or "" for node in paragraph.findall(".//w:t", namespace))
                         for paragraph in root.findall(".//w:p", namespace))
    if ext == "zip":
        return read_zip_text(data)
    return data.decode("utf-8", errors="replace")


def _prepare_source(session: Session, source: KnowledgeSource, github_token: str = "") -> None:
    if session.exec(select(KnowledgeChunk).where(KnowledgeChunk.source_id == source.id)).first():
        return
    if source.kind == "github":
        text, overview = public_repo_overview(source.meta["url"], github_token)
        cleaned, count = redact(text[:500000])
        source.size = len(cleaned.encode())
        source.sha256 = hashlib.sha256(cleaned.encode()).hexdigest()
        source.meta = {**source.meta, "redacted_count": count, "repo_profile": overview}
    else:
        if not source.path:
            return
        path = Path(source.path)
        if not path.is_file():
            raise ValueError("材料文件不存在")
        ext = path.suffix.lstrip(".").lower()
        text = _parse_uploaded_material(path.read_bytes(), ext)
        cleaned, count = redact(text[:500000])
        meta = {**source.meta, "redacted_count": count}
        if ext == "zip":
            meta["repo_profile"] = profile_from_text(cleaned)
        source.meta = meta
    for i, part in enumerate(chunk_text(cleaned)):
        session.add(KnowledgeChunk(source_id=source.id, user_id=source.user_id, ord=i, text=part))
    session.add(source)
    session.commit()


def _queue_extraction(background: BackgroundTasks, session: Session, user_id: int, source_id: int,
                      workflow_id: str | None = None, github_token: str = "") -> str:
    """Run candidate extraction after response, using the shared bounded task queue."""
    workflow = session.get(WorkflowRun, workflow_id) if workflow_id else start(session, user_id, "knowledge_ingest", {"source_id": source_id})
    if workflow is None or workflow.user_id != user_id or workflow.subject.get("source_id") != source_id:
        raise ValueError("工作流与材料不匹配")
    def work(report):
        try:
            with Session(engine) as s:
                source = s.get(KnowledgeSource, source_id)
                if not source or source.user_id != user_id:
                    return {"source_id": source_id, "proposed": 0}
                source.status = "processing"
                s.add(source)
                s.commit()
                report(5, "解析材料并建立索引")
                _prepare_source(s, source, github_token)
                run = s.get(WorkflowRun, workflow.id)
                def extract():
                    chunks = s.exec(select(KnowledgeChunk).where(KnowledgeChunk.source_id == source_id,
                                                                  KnowledgeChunk.user_id == user_id).order_by(KnowledgeChunk.ord)).all()
                    existing = s.exec(select(EvidenceClaim).where(EvidenceClaim.user_id == user_id)).all()
                    seen = {(claim.statement.strip().lower(), tuple(claim.source_chunk_ids)) for claim in existing}
                    added = 0
                    batches = [chunks[index:index + 8] for index in range(0, min(len(chunks), 240), 8)]
                    for index, batch in enumerate(batches):
                        report(int(90 * index / max(len(batches), 1)), f"提取事实 {index + 1}/{len(batches)} 批")
                        out = invoke(EXTRACT, materials={"knowledge_chunk": "\n\n".join(chunk.text for chunk in batch)},
                                     ctx=agent_ctx(user_id, "knowledge")).output
                        for item in out.claims[:20]:
                            statement, quote = item.statement.strip(), item.quote.strip()
                            chunk = next((part for part in batch if quote and quote in part.text), None)
                            if chunk is None:
                                continue
                            key = (statement.lower(), (chunk.id,))
                            if not statement or key in seen:
                                continue
                            s.add(EvidenceClaim(user_id=user_id, statement=statement[:2000], claim_type=item.claim_type[:40],
                                                source_chunk_ids=[chunk.id], source_quote=quote[:2000], status="proposed",
                                                level="L2", origin="extracted", confidence=1.0,
                                                project_id=source.linked_project_ids[0] if len(source.linked_project_ids) == 1 else ""))
                            seen.add(key)
                            added += 1
                    source.status = "ready"
                    s.add(source)
                    s.flush()
                    return added, f"读取 {len(chunks)} 个片段，提议 {added} 条事实", []
                added = execute_step(s, run, "事实已抽取", extract, f"材料 {source_id}", terminal=False, node_type="agent")
                if added:
                    wait_gate(s, run, "等待事实确认", f"请确认或拒绝 {added} 条候选事实")
                else:
                    skip_gate(s, run, "等待事实确认", "没有新的候选事实")
                    run.status, run.finished_at = "done", datetime.now(timezone.utc)
                    s.add(run)
                    s.commit()
                return {"source_id": source_id, "proposed": added, "workflow_id": run.id}
        except Exception as exc:
            with Session(engine) as s:
                source = s.get(KnowledgeSource, source_id)
                if source and source.user_id == user_id:
                    source.status, source.error = "failed", str(exc)[:300]
                    s.add(source)
                    s.commit()
            raise
    return submit(background, session, user_id, "knowledge:extract", work).id


def _finish_confirmed_source_workflows(session: Session, user_id: int, changed_claims: list[EvidenceClaim]) -> None:
    chunk_ids = {chunk_id for claim in changed_claims for chunk_id in claim.source_chunk_ids}
    if not chunk_ids:
        return
    chunks = session.exec(select(KnowledgeChunk).where(KnowledgeChunk.user_id == user_id,
                                                        KnowledgeChunk.id.in_(chunk_ids))).all()
    source_ids = {chunk.source_id for chunk in chunks}
    runs = session.exec(select(WorkflowRun).where(WorkflowRun.user_id == user_id,
                                                 WorkflowRun.kind == "knowledge_ingest",
                                                 WorkflowRun.status == "waiting_user")).all()
    claims = session.exec(select(EvidenceClaim).where(EvidenceClaim.user_id == user_id,
                                                       EvidenceClaim.status == "proposed")).all()
    proposed_chunk_ids = {chunk_id for claim in claims for chunk_id in claim.source_chunk_ids}
    for run in runs:
        source_id = run.subject.get("source_id")
        if source_id not in source_ids:
            continue
        source_chunks = session.exec(select(KnowledgeChunk).where(KnowledgeChunk.source_id == source_id,
                                                                  KnowledgeChunk.user_id == user_id)).all()
        if any(chunk.id in proposed_chunk_ids for chunk in source_chunks):
            continue
        resume_gate(session, run, "候选事实已处理")
        run.status, run.finished_at = "done", datetime.now(timezone.utc)
        session.add(run)
    session.flush()


@router.post("/sources/{source_id}/extract")
def extract_claims(source_id: int, background: BackgroundTasks, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)):
    source = session.exec(select(KnowledgeSource).where(KnowledgeSource.id == source_id,
                                                        KnowledgeSource.user_id == user.id)).first()
    if not source:
        raise HTTPException(404, "材料不存在")
    return {"task_id": _queue_extraction(background, session, user.id, source_id)}


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    source = session.exec(select(KnowledgeSource).where(KnowledgeSource.id == source_id,
                                                        KnowledgeSource.user_id == user.id)).first()
    if not source:
        raise HTTPException(404, "材料不存在")
    chunks = session.exec(select(KnowledgeChunk).where(KnowledgeChunk.source_id == source_id,
                                                       KnowledgeChunk.user_id == user.id)).all()
    chunk_ids = {chunk.id for chunk in chunks}
    claims = session.exec(select(EvidenceClaim).where(EvidenceClaim.user_id == user.id)).all()
    for claim in claims:
        if chunk_ids.intersection(claim.source_chunk_ids):
            session.delete(claim)
            invalidate_evidence_for_user(session, user.id)
    for chunk in chunks:
        session.delete(chunk)
    if source.path:
        candidate = Path(source.path).resolve()
        root = (UPLOAD_DIR / str(user.id) / "knowledge").resolve()
        if root in candidate.parents:
            candidate.unlink(missing_ok=True)
    session.delete(source)
    session.commit()
    return {"ok": True}


@router.get("/search")
def search(q: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    query = q.strip()[:100]
    if not query:
        return []
    return search_chunks(session, user.id, query)


@router.get("/claims")
def list_claims(status: str = "proposed", user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return session.exec(select(EvidenceClaim).where(EvidenceClaim.user_id == user.id,
                                                    EvidenceClaim.status == status)).all()


@router.post("/claims/batch")
def batch_claims(body: BatchClaims, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if body.action not in {"confirm", "reject"}:
        raise HTTPException(422, "action 必须为 confirm 或 reject")
    rows = session.exec(select(EvidenceClaim).where(EvidenceClaim.user_id == user.id,
                                                    EvidenceClaim.id.in_(body.ids))).all()
    if len(rows) != len(set(body.ids)) or any(row.status != "proposed" for row in rows):
        raise HTTPException(409, "包含不存在或已经处理的事实")
    for row in rows:
        row.status = "confirmed" if body.action == "confirm" else "rejected"
        if body.action == "confirm":
            row.level, row.confirmed_at = "L1", datetime.now(timezone.utc)
        session.add(row)
    if body.action == "confirm":
        invalidate_evidence_for_user(session, user.id)
    _finish_confirmed_source_workflows(session, user.id, rows)
    session.commit()
    return {"updated": len(rows)}


@router.post("/claims/{claim_id}/confirm")
def confirm_claim(claim_id: int, body: ConfirmBody, user: User = Depends(get_current_user),
                  session: Session = Depends(get_session)):
    claim = session.exec(select(EvidenceClaim).where(EvidenceClaim.id == claim_id,
                                                      EvidenceClaim.user_id == user.id)).first()
    if not claim:
        raise HTTPException(404, "事实不存在")
    if body.statement:
        claim.statement = body.statement.strip()
    if body.project_id:
        from agents.core.schemas import iter_projects
        from backend.app.services.jobs import load_profile
        valid_ids = {project.id for project, _ in iter_projects(load_profile(session, user.id))}
        if body.project_id not in valid_ids:
            raise HTTPException(422, "项目不存在")
        claim.project_id = body.project_id
    claim.status, claim.level, claim.confirmed_at = "confirmed", "L1", datetime.now(timezone.utc)
    session.add(claim)
    invalidate_evidence_for_user(session, user.id)
    _finish_confirmed_source_workflows(session, user.id, [claim])
    session.commit()
    return claim


@router.post("/claims/{claim_id}/reject")
def reject_claim(claim_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    claim = session.exec(select(EvidenceClaim).where(EvidenceClaim.id == claim_id,
                                                      EvidenceClaim.user_id == user.id)).first()
    if not claim:
        raise HTTPException(404, "事实不存在")
    claim.status = "rejected"
    session.add(claim)
    _finish_confirmed_source_workflows(session, user.id, [claim])
    session.commit()
    return claim
