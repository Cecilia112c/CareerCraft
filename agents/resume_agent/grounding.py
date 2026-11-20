"""Sentence-level grounding against only the evidence cited by that sentence."""

from __future__ import annotations

from agents.resume_agent.check import check_text


def verify_grounded(text: str, evidence_ids: list[str], evidence: dict[str, dict]) -> list[str]:
    """Reject unknown/L2 references and numbers or technical terms absent from cited L1 facts."""
    if not text.strip():
        return ["内容为空"]
    if not evidence_ids:
        return ["缺少依据引用"]
    invalid = [key for key in evidence_ids if key not in evidence or evidence[key].get("level") != "L1"]
    if invalid:
        return ["引用了不存在或未经确认的事实依据"]
    reference = "\n".join(evidence[key]["statement"] for key in dict.fromkeys(evidence_ids))
    return check_text(text, reference)
