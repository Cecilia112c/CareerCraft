"""User-scoped SQLite FTS5 trigram retrieval."""

import re

from sqlalchemy import text
from sqlmodel import Session, select

from agents.core.schemas import ProfileData, _text_items
from backend.app.models import EvidenceClaim, KnowledgeChunk, Profile


def search_chunks(session: Session, user_id: int, query: str, limit: int = 20) -> list[KnowledgeChunk]:
    query = query.strip()[:100]
    if not query:
        return []
    if len(query) < 3:
        return session.exec(select(KnowledgeChunk).where(KnowledgeChunk.user_id == user_id,
                                                         KnowledgeChunk.text.contains(query)).limit(limit)).all()
    phrase = '"' + query.replace('"', '""') + '"'
    ids = session.execute(text("SELECT chunk_id FROM knowledge_fts WHERE knowledge_fts MATCH :query AND user_id=:user_id ORDER BY rank LIMIT :limit"),
                          {"query": phrase, "user_id": user_id, "limit": limit}).scalars().all()
    rows = {row.id: row for row in session.exec(select(KnowledgeChunk).where(KnowledgeChunk.user_id == user_id,
                                                                     KnowledgeChunk.id.in_(ids))).all()} if ids else {}
    return [rows[id_] for id_ in ids if id_ in rows]


def retrieve_l1_evidence(session: Session, user_id: int, brief: dict, per_requirement: int = 5) -> list[dict]:
    """Top-k candidate facts per requirement; raw chunks influence ranking but are never cited."""
    profile_row = session.exec(select(Profile).where(Profile.user_id == user_id)).first()
    profile = ProfileData.model_validate(profile_row.data) if profile_row else ProfileData()
    facts = [{"id": f"profile:{item.id}", "statement": item.text, "level": "L1", "status": "confirmed",
              "source_chunk_ids": []} for item in _text_items(profile) if item.text.strip()]
    for key, value in (("basic.headline", profile.basic.headline),
                       ("basic.summary", profile.basic.summary), ("skills", "、".join(profile.skills))):
        if value.strip():
            facts.append({"id": f"profile:{key}", "statement": value, "level": "L1",
                          "status": "confirmed", "source_chunk_ids": []})
    claims = session.exec(select(EvidenceClaim).where(EvidenceClaim.user_id == user_id,
                                                     EvidenceClaim.status == "confirmed",
                                                     EvidenceClaim.level == "L1")).all()
    facts += [{"id": f"claim:{claim.id}", "statement": claim.statement, "level": "L1",
               "status": "confirmed", "source_chunk_ids": claim.source_chunk_ids} for claim in claims]
    selected: dict[str, dict] = {}
    for requirement in brief.get("requirements", []):
        terms = {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]*|[\u4e00-\u9fff]{2,}",
                                                        requirement.get("text", ""))}
        terms.update(str(skill).lower() for skill in requirement.get("skills", []))
        chunk_ids: set[int] = set()
        if any(fact["source_chunk_ids"] for fact in facts):
            for skill in requirement.get("skills", [])[:3]:
                if len(skill) >= 2:
                    chunk_ids.update(chunk.id for chunk in search_chunks(session, user_id, skill, limit=10))
        ranked = []
        for fact in facts:
            statement = fact["statement"].lower()
            shared = sum(1 for term in terms if term and term in statement)
            source_hit = bool(chunk_ids.intersection(fact["source_chunk_ids"]))
            if shared or source_hit:
                ranked.append((shared + (3 if source_hit else 0), fact))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        for _, fact in ranked[:per_requirement]:
            selected[fact["id"]] = {key: value for key, value in fact.items() if key != "source_chunk_ids"}
    return list(selected.values())[:80]
