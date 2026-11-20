from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.auth import hash_password
from backend.app.models import KnowledgeChunk, KnowledgeSource, Profile, User
from backend.app.routers.auth import DeleteAccountBody, delete_account


def test_account_delete_removes_knowledge_files_and_memory(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("backend.app.routers.auth.UPLOAD_DIR", tmp_path)
    with Session(engine) as session:
        user = User(username="delete-test", password_hash=hash_password("secret123"))
        session.add(user)
        session.commit()
        session.refresh(user)
        session.add(Profile(user_id=user.id, data={}))
        source = KnowledgeSource(user_id=user.id, kind="note", title="测试")
        session.add(source)
        session.commit()
        session.refresh(source)
        session.add(KnowledgeChunk(source_id=source.id, user_id=user.id, ord=0, text="内容"))
        session.commit()
        folder = tmp_path / str(user.id) / "knowledge"
        folder.mkdir(parents=True)
        (folder / "sample.txt").write_text("content", encoding="utf-8")
        assert delete_account(DeleteAccountBody(password="secret123"), user, session) == {"ok": True}
        assert not session.exec(select(KnowledgeSource)).all()
        assert not session.exec(select(KnowledgeChunk)).all()
        assert not folder.exists()
