"""Server-side validation of resume evidence references."""

from fastapi import HTTPException
from sqlmodel import Session, select

from agents.core.schemas import ProfileData, ResumeDoc, _text_items
from agents.resume_agent.grounding import verify_grounded
from backend.app.models import EvidenceClaim, Profile


def validate_resume_citations(session: Session, user_id: int, doc: ResumeDoc) -> None:
    cited = {ref for item in _text_items(doc) for ref in item.evidence_ids}
    cited.update(doc.basic.headline_evidence_ids)
    cited.update(doc.basic.summary_evidence_ids)
    if not cited:
        return
    claims = session.exec(select(EvidenceClaim).where(EvidenceClaim.user_id == user_id,
                                                     EvidenceClaim.status == "confirmed",
                                                     EvidenceClaim.level == "L1")).all()
    evidence = {f"claim:{claim.id}": {"statement": claim.statement, "level": "L1"} for claim in claims}
    profile = session.exec(select(Profile).where(Profile.user_id == user_id)).first()
    if profile:
        data = ProfileData.model_validate(profile.data)
        evidence.update({f"profile:{item.id}": {"statement": item.text, "level": "L1"}
                         for item in _text_items(data)})
        evidence["profile:basic.headline"] = {"statement": data.basic.headline, "level": "L1"}
        evidence["profile:basic.summary"] = {"statement": data.basic.summary, "level": "L1"}
        evidence["profile:skills"] = {"statement": "、".join(data.skills), "level": "L1"}
    if cited - set(evidence):
        raise HTTPException(422, "简历引用了不存在或未经确认的事实依据")
    for item in _text_items(doc):
        if item.evidence_ids and verify_grounded(item.text, item.evidence_ids, evidence):
            raise HTTPException(422, "简历正文包含未被所引依据支持的数字或技术词")
    for value, refs in ((doc.basic.headline, doc.basic.headline_evidence_ids),
                        (doc.basic.summary, doc.basic.summary_evidence_ids)):
        if refs and verify_grounded(value, refs, evidence):
            raise HTTPException(422, "个人简介包含未被所引依据支持的数字或技术词")
