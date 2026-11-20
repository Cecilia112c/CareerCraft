from typing import Iterator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from backend.app.config import DATA_DIR

engine = create_engine(
    f"sqlite:///{(DATA_DIR / 'careercraft.db').as_posix()}",
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# create_all 不会给已存在的表加新列：这里列出后来新增的列，启动时自动补上（简易迁移）
_ADDED_COLUMNS = {
    "job": {
        "site": "TEXT NOT NULL DEFAULT ''",
        "origin": "TEXT NOT NULL DEFAULT 'legacy'",
        "detail_level": "TEXT NOT NULL DEFAULT 'summary'",
        "status": "TEXT NOT NULL DEFAULT 'saved'",
        "status_history": "JSON NOT NULL DEFAULT '[]'",
        "notes": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "DATETIME",
        "brief_artifact_id": "TEXT NOT NULL DEFAULT ''",
        "raw_sha256": "TEXT NOT NULL DEFAULT ''",
    },
    "pushsetting": {
        "sources": "JSON NOT NULL DEFAULT '[\"boss\",\"tencent\",\"bytedance\",\"alibaba\",\"huawei\",\"shixiseng\"]'",
        "salary_min": "INTEGER NOT NULL DEFAULT 0",
        "salary_max": "INTEGER NOT NULL DEFAULT 0",
        "top_n": "INTEGER NOT NULL DEFAULT 10",
    },
    "resume": {"artifact_id": "TEXT NOT NULL DEFAULT ''"},
    "evidenceclaim": {"project_id": "TEXT NOT NULL DEFAULT ''", "source_quote": "TEXT NOT NULL DEFAULT ''"},
    "interview": {"source_type": "TEXT NOT NULL DEFAULT ''", "source_id": "INTEGER",
                  "source_version": "INTEGER", "round": "INTEGER NOT NULL DEFAULT 1",
                  "previous_interview_id": "INTEGER", "mode": "TEXT NOT NULL DEFAULT 'blind'",
                  "brief_artifact_id": "TEXT NOT NULL DEFAULT ''"},
    "artifact": {"schema_version": "TEXT NOT NULL DEFAULT '1'"},
    "resumeversion": {"evidence_artifact_id": "TEXT NOT NULL DEFAULT ''"},
    "knowledgesource": {"error": "TEXT NOT NULL DEFAULT ''",
                        "linked_project_ids": "JSON NOT NULL DEFAULT '[]'"},
    "workflowstep": {"ordinal": "INTEGER NOT NULL DEFAULT 0"},
}


def _migrate() -> None:
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if not existing:
                continue
            for name, ddl in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db() -> None:
    from backend.app import models  # noqa: F401  (register tables)
    SQLModel.metadata.create_all(engine)
    _migrate()
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(chunk_id UNINDEXED, user_id UNINDEXED, text, tokenize='trigram')")
        conn.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS knowledge_fts_insert AFTER INSERT ON knowledgechunk BEGIN INSERT INTO knowledge_fts(chunk_id,user_id,text) VALUES (new.id,new.user_id,new.text); END")
        conn.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS knowledge_fts_delete AFTER DELETE ON knowledgechunk BEGIN DELETE FROM knowledge_fts WHERE chunk_id=old.id; END")
        conn.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS knowledge_fts_update AFTER UPDATE ON knowledgechunk BEGIN DELETE FROM knowledge_fts WHERE chunk_id=old.id; INSERT INTO knowledge_fts(chunk_id,user_id,text) VALUES (new.id,new.user_id,new.text); END")
        conn.exec_driver_sql("INSERT INTO knowledge_fts(chunk_id,user_id,text) SELECT k.id,k.user_id,k.text FROM knowledgechunk k WHERE NOT EXISTS (SELECT 1 FROM knowledge_fts f WHERE f.chunk_id=k.id)")


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
