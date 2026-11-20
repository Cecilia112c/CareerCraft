"""Deterministic Plan D citation and feedback baseline, without sending user data to a model."""

from __future__ import annotations

import json
from collections import Counter

from sqlmodel import Session, select

from agents.core.schemas import ProfileData, ResumeDoc, _text_items
from agents.resume_agent.grounding import verify_grounded
from backend.app.db import engine
from backend.app.models import EvidenceClaim, MaterialRequest, Profile, Resume, ResumeVersion


def evaluate(session: Session) -> dict:
    profiles = {row.user_id: row for row in session.exec(select(Profile)).all()}
    resumes = {row.id: row for row in session.exec(select(Resume)).all()}
    claims_by_user: dict[int, dict] = {}
    for claim in session.exec(select(EvidenceClaim)).all():
        claims_by_user.setdefault(claim.user_id, {})[f"claim:{claim.id}"] = {
            "statement": claim.statement, "level": claim.level if claim.status == "confirmed" else "L2"}
    counts: Counter = Counter()
    for version in session.exec(select(ResumeVersion)).all():
        resume = resumes.get(version.resume_id)
        if not resume:
            continue
        counts["versions"] += 1
        try:
            doc = ResumeDoc.model_validate(version.data)
            profile = ProfileData.model_validate(profiles[resume.user_id].data) if resume.user_id in profiles else ProfileData()
        except Exception:
            counts["unreadable_versions"] += 1
            continue
        evidence = {**{f"profile:{item.id}": {"statement": item.text, "level": "L1"}
                       for item in _text_items(profile)}, **claims_by_user.get(resume.user_id, {})}
        evidence.update({"profile:basic.headline": {"statement": profile.basic.headline, "level": "L1"},
                         "profile:basic.summary": {"statement": profile.basic.summary, "level": "L1"},
                         "profile:skills": {"statement": "、".join(profile.skills), "level": "L1"}})
        entries = [(item.text, item.evidence_ids) for item in _text_items(doc)]
        entries += [(doc.basic.headline, doc.basic.headline_evidence_ids),
                    (doc.basic.summary, doc.basic.summary_evidence_ids)]
        for value, refs in entries:
            if not value.strip():
                continue
            counts["sentences"] += 1
            if not refs:
                counts["uncited_sentences"] += 1
                continue
            counts["cited_sentences"] += 1
            counts["citations"] += len(refs)
            counts["valid_citations"] += sum(ref in evidence and evidence[ref]["level"] == "L1"
                                             for ref in refs)
            counts["l2_misuse"] += sum(ref in evidence and evidence[ref]["level"] != "L1"
                                       for ref in refs)
            if not verify_grounded(value, refs, evidence):
                counts["grounded_sentences"] += 1
    requests = session.exec(select(MaterialRequest)).all()
    counts["requests"] = len(requests)
    counts["resolved_requests"] = sum(request.status == "resolved" for request in requests)
    return dict(counts) | {
        "citation_validity_rate": round(counts["valid_citations"] / counts["citations"], 4) if counts["citations"] else None,
        "l2_misuse_rate": round(counts["l2_misuse"] / counts["citations"], 4) if counts["citations"] else None,
        "sentence_grounding_rate": round(counts["grounded_sentences"] / counts["cited_sentences"], 4) if counts["cited_sentences"] else None,
        "request_resolution_rate": round(counts["resolved_requests"] / counts["requests"], 4) if counts["requests"] else None,
    }


if __name__ == "__main__":
    with Session(engine) as db_session:
        print(json.dumps(evaluate(db_session), ensure_ascii=False, indent=2))
