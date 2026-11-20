"""Back up the business DB, then import legacy PDF documents into the knowledge library.

Run with the backend stopped: python scripts/migrate_plan_d.py
The old Document rows and files remain for read compatibility. Re-running is idempotent.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, select

from backend.app.config import DATA_DIR, UPLOAD_DIR
from backend.app.db import engine, init_db
from backend.app.knowledge.safety import chunk_text, redact
from backend.app.models import Document, KnowledgeChunk, KnowledgeSource


def migrate(session: Session) -> int:
    existing = session.exec(select(KnowledgeSource)).all()
    migrated_ids = {source.meta.get("legacy_document_id") for source in existing}
    count = 0
    for doc in session.exec(select(Document)).all():
        if doc.id in migrated_ids:
            continue
        raw_path = Path(doc.path)
        data = raw_path.read_bytes() if raw_path.is_file() else b""
        cleaned, redacted_count = redact(doc.text or "")
        source = KnowledgeSource(user_id=doc.user_id, kind="resume", title=doc.filename,
                                 filename=doc.filename, size=len(data),
                                 sha256=hashlib.sha256(data or cleaned.encode()).hexdigest(),
                                 status="ready", meta={"legacy_document_id": doc.id,
                                                       "redacted_count": redacted_count})
        session.add(source)
        session.flush()
        if data:
            folder = UPLOAD_DIR / str(doc.user_id) / "knowledge"
            folder.mkdir(parents=True, exist_ok=True)
            destination = folder / f"{source.id}.pdf"
            shutil.copyfile(raw_path, destination)
            source.path = str(destination)
        for index, part in enumerate(chunk_text(cleaned)):
            session.add(KnowledgeChunk(source_id=source.id, user_id=doc.user_id,
                                       ord=index, text=part))
        session.add(source)
        count += 1
    session.commit()
    return count


def main() -> None:
    db_path = DATA_DIR / "careercraft.db"
    if not db_path.exists():
        print("Database does not exist; nothing to migrate.")
        return
    backup = Path(f"{db_path}.plan-d-{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak")
    with sqlite3.connect(db_path) as original, sqlite3.connect(backup) as target:
        original.backup(target)
    print(f"Backup: {backup}")
    init_db()
    with Session(engine) as session:
        print(f"Imported {migrate(session)} legacy documents.")


if __name__ == "__main__":
    main()
