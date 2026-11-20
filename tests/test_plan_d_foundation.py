"""PLAN-D boundaries: JD cannot receive candidate data; artifacts retain lineage."""

import pytest
import io
import zipfile
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from agents.harness import invoke
from agents.jd_agent.specs import NORMALIZE
from backend.app.models import Artifact
from backend.app.workflows.artifacts import invalidate_evidence_for_user, save_artifact
from backend.app.knowledge.safety import read_zip_text, redact
from backend.app.knowledge.retrieval import search_chunks
from backend.app.knowledge.repo_profile import profile_from_text
from backend.app.knowledge.github import repository_parts
from backend.app.models import KnowledgeChunk
from backend.app.models import EvidenceClaim
from backend.app.services.evidence import validate_resume_citations
from agents.core.schemas import ResumeDoc
from agents.core.schemas import Project
from agents.resume_agent.agent import _rewrite_project
from agents.resume_agent.specs import POLISH
from agents.harness import ExecutionContext
from agents.harness.tools import ToolPolicy, default_registry
from backend.app.agent_tools.knowledge_search import SearchKnowledgeTool
from fastapi import HTTPException
from agents.resume_agent.match import match_requirements, match_with_agent
from agents.feedback.extract import propose_requests


def test_jd_context_rejects_candidate_data_before_model_call(llm):
    with pytest.raises(ValueError, match="outside context contract"):
        invoke(NORMALIZE, materials={"job_page": "岗位描述", "profile": "私人简历"})
    assert not llm.calls
    with pytest.raises(ValueError, match="variables outside context contract"):
        invoke(NORMALIZE, variables={"profile": "私人简历"}, materials={"job_page": "岗位描述"})
    assert not llm.calls


def test_artifact_versions_invalidate_downstream():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        first = save_artifact(session, 1, "JobBrief", {"job_id": 10}, {"requirements": [{"req_id": "r1", "text": "Python"}]}, {"agent": "jd"})
        dependent = save_artifact(session, 1, "ResumeEvidence", {"job_id": 10}, {"matches": []},
                                  {"agent": "resume"}, inputs=[{"id": first.id, "version": first.version}])
        second = save_artifact(session, 1, "JobBrief", {"job_id": 10}, {"requirements": [{"req_id": "r1", "text": "Go"}]}, {"agent": "jd"})
        assert second.version == 2
        assert session.get(Artifact, first.id).status == "superseded"
        assert session.get(Artifact, dependent.id).status == "stale"


def test_zip_rejects_traversal_and_redacts_secret():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../escape.py", "print('bad')")
    with pytest.raises(ValueError, match="不安全"):
        read_zip_text(stream.getvalue())
    for unsafe_name in ("C:/outside.py", "\\\\server\\share\\outside.py"):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr(unsafe_name, "print('bad')")
        with pytest.raises(ValueError, match="不安全"):
            read_zip_text(stream.getvalue())
    cleaned, count = redact("API_KEY=sk-abcdefghijklmnopqrstuvwxyz\n")
    assert count >= 1 and "abcdefghijklmnopqrstuvwxyz" not in cleaned


def test_unconfirmed_claim_cannot_cover_requirement():
    brief = {"requirements": [{"req_id": "r1", "text": "需要 Python 开发经验", "skills": ["Python"]}]}
    claims = [{"id": "claim:1", "statement": "使用 Python 开发接口", "level": "L2", "status": "proposed"}]
    assert match_requirements(brief, claims)["matches"][0]["coverage"] == "none"
    claims[0].update(level="L1", status="confirmed")
    assert match_requirements(brief, claims)["matches"][0]["coverage"] == "partial"


def test_match_agent_cannot_cite_other_requirement_or_unconfirmed_fact(llm):
    brief = {"requirements": [{"req_id": "r1", "text": "需要 Python 开发经验", "skills": ["Python"]},
                              {"req_id": "r2", "text": "需要 Kafka 经验", "skills": ["Kafka"]}]}
    evidence = [{"id": "claim:1", "statement": "使用 Python 开发服务", "level": "L1", "status": "confirmed"},
                {"id": "claim:2", "statement": "使用 Kafka 处理消息", "level": "L2", "status": "proposed"}]
    llm.push({"matches": [{"req_id": "r1", "coverage": "strong", "evidence_ids": ["claim:1"], "reason": "明确使用"},
                          {"req_id": "r2", "coverage": "strong", "evidence_ids": ["claim:2"], "reason": "伪造"}]})
    result = match_with_agent(brief, evidence)
    assert result["matches"][0]["coverage"] == "strong"
    assert result["matches"][1]["coverage"] == "none"


def test_interview_feedback_only_proposes():
    requests = propose_requests({"risks": ["缺少性能数据"]}, 4, 8)
    assert requests[0]["status"] == "proposed"
    assert requests[0]["target"]["interview_id"] == 4


def test_fts_search_is_user_scoped():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE VIRTUAL TABLE knowledge_fts USING fts5(chunk_id UNINDEXED,user_id UNINDEXED,text,tokenize='trigram')")
    with Session(engine) as session:
        a = KnowledgeChunk(source_id=1, user_id=1, ord=0, text="使用 Python 构建检索服务")
        b = KnowledgeChunk(source_id=2, user_id=2, ord=0, text="使用 Python 构建检索服务")
        session.add_all([a, b])
        session.commit()
        session.execute(__import__("sqlalchemy").text("INSERT INTO knowledge_fts(chunk_id,user_id,text) VALUES (:id,:uid,:text)"),
                        [{"id": a.id, "uid": 1, "text": a.text}, {"id": b.id, "uid": 2, "text": b.text}])
        session.commit()
        assert [row.id for row in search_chunks(session, 1, "Python")] == [a.id]


def test_resume_citation_requires_confirmed_owner_fact():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        claim = EvidenceClaim(user_id=2, statement="用 Python 开发", status="confirmed", level="L1")
        session.add(claim)
        session.commit()
        doc = ResumeDoc.model_validate({"education": [{"bullets": [{"text": "用 Python 开发", "evidence_ids": [f"claim:{claim.id}"]}]}]})
        with pytest.raises(HTTPException):
            validate_resume_citations(session, 1, doc)
        validate_resume_citations(session, 2, doc)


def test_confirmed_fact_to_match_to_stale_chain():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        brief = save_artifact(session, 7, "JobBrief", {"job_id": 3},
                              {"requirements": [{"req_id": "r1", "text": "Python 开发", "skills": ["Python"]}]},
                              {"agent": "jd"})
        claim = EvidenceClaim(user_id=7, statement="使用 Python 开发接口", status="proposed", level="L2")
        session.add(claim)
        session.commit()
        candidate = {"id": f"claim:{claim.id}", "statement": claim.statement,
                     "status": claim.status, "level": claim.level}
        assert match_requirements(brief.body, [candidate])["matches"][0]["coverage"] == "none"
        claim.status, claim.level = "confirmed", "L1"
        session.add(claim)
        session.commit()
        candidate.update(status="confirmed", level="L1")
        result = match_requirements(brief.body, [candidate])
        assert result["matches"][0]["evidence"][0]["evidence_id"] == f"claim:{claim.id}"
        matched = save_artifact(session, 7, "ResumeEvidence", {"job_id": 3}, result, {"agent": "resume"},
                                inputs=[{"id": brief.id, "version": brief.version}])
        draft = save_artifact(session, 7, "ResumeDraft", {"resume_id": 2}, {"version": 1}, {"agent": "resume"},
                              inputs=[{"id": matched.id, "version": matched.version}])
        invalidate_evidence_for_user(session, 7)
        session.commit()
        assert session.get(Artifact, matched.id).status == "stale"
        assert session.get(Artifact, draft.id).status == "stale"


def test_repo_profile_uses_only_accepted_files():
    overview = profile_from_text("## app/main.py\nfrom fastapi import FastAPI\n## frontend/App.vue\nVue\n## tests/test_api.py\npytest\n")
    assert overview["file_count"] == 3
    assert overview["has_tests"]
    assert "fastapi" in overview["frameworks"]


def test_generation_requires_citation_for_new_technical_fact(llm):
    project = Project.model_validate({"id": "p1", "name": "项目", "responsibilities": [{"id": "b1", "text": "参与接口开发"}]})
    claim = {"id": "claim:8", "statement": "使用 Kafka 实现消息队列", "project_id": "p1"}
    llm.push({"background": [], "responsibilities": [{"id": "b1", "text": "使用 Kafka 实现消息队列", "evidence_ids": []}],
              "impact": [], "keywords": []})
    unchanged, warnings = _rewrite_project(project, "项目", None, [], None, [claim])
    assert unchanged.responsibilities[0].text == "参与接口开发"
    assert warnings
    llm.push({"background": [], "responsibilities": [{"id": "b1", "text": "使用 Kafka 实现消息队列", "evidence_ids": ["claim:8"]}],
              "impact": [], "keywords": []})
    changed, warnings = _rewrite_project(project, "项目", None, [], None, [claim])
    assert changed.responsibilities[0].text == "使用 Kafka 实现消息队列"
    assert "claim:8" in changed.responsibilities[0].evidence_ids


def test_knowledge_search_visible_only_with_kb_scope():
    registry = default_registry()
    registry.register(SearchKnowledgeTool())
    policy = ToolPolicy()
    without = policy.visible(POLISH, ExecutionContext.for_user(1, scopes={"material:read"}), registry)
    with_scope = policy.visible(POLISH, ExecutionContext.for_user(1, scopes={"kb:read"}), registry)
    assert "search_knowledge" not in without
    assert "search_knowledge" in with_scope


def test_github_url_rejects_other_hosts():
    assert repository_parts("https://github.com/example/repo") == ("example", "repo")
    with pytest.raises(ValueError):
        repository_parts("https://github.com.evil.example/example/repo")
