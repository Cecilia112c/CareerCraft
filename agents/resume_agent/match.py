"""Conservative requirement-to-evidence matching; only confirmed facts are eligible."""

import re

from agents.harness import ExecutionContext, invoke
from agents.resume_agent.specs import MATCH


def _tokens(text: str) -> set[str]:
    return {part.lower() for part in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]*|[\u4e00-\u9fff]{2,}", text)
            if len(part) >= 2}


def match_requirements(brief: dict, evidence: list[dict]) -> dict:
    confirmed = [item for item in evidence if item.get("level") == "L1" and item.get("status") == "confirmed"]
    matches = []
    for requirement in brief.get("requirements", []):
        target = _tokens(requirement.get("text", "")) | {s.lower() for s in requirement.get("skills", [])}
        ranked = []
        for item in confirmed:
            shared = target & _tokens(item.get("statement", ""))
            if shared:
                ranked.append((len(shared), item))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        refs = [{"evidence_id": row["id"], "statement": row["statement"], "shared_terms": count}
                for count, row in ranked[:3]]
        matches.append({"req_id": requirement["req_id"], "requirement": requirement["text"],
                        "coverage": "partial" if refs else "none", "evidence": refs,
                        "reason": "有相关的已确认事实，仍需人工核对是否完全满足要求" if refs else "没有找到相关的已确认事实"})
    return {"job_id": brief.get("job_id"), "matches": matches,
            "missing_req_ids": [row["req_id"] for row in matches if row["coverage"] == "none"]}


def match_with_agent(brief: dict, evidence: list[dict], ctx: ExecutionContext | None = None) -> dict:
    """Let the agent judge the small candidate set; code enforces the L1 reference boundary."""
    baseline = match_requirements(brief, evidence)
    candidates = {ref["evidence_id"] for row in baseline["matches"] for ref in row["evidence"]}
    if not candidates:
        return baseline
    allowed = {item["id"]: item for item in evidence if item.get("id") in candidates
               and item.get("level") == "L1" and item.get("status") == "confirmed"}
    try:
        output = invoke(MATCH,
                        materials={"job_brief": {"requirements": brief.get("requirements", [])},
                                   "confirmed_evidence": [{"evidence_id": key, "statement": value["statement"]}
                                                          for key, value in list(allowed.items())[:60]]},
                        ctx=ctx).output
    except Exception:
        return baseline
    decisions = {item.req_id: item for item in output.matches}
    for match in baseline["matches"]:
        decision = decisions.get(match["req_id"])
        if not decision:
            continue
        candidates_for_req = {ref["evidence_id"]: ref for ref in match["evidence"]}
        selected = [candidates_for_req[key] for key in dict.fromkeys(decision.evidence_ids)
                    if key in candidates_for_req and key in allowed]
        if not selected:
            continue
        requirement = next((req for req in brief.get("requirements", []) if req.get("req_id") == match["req_id"]), {})
        skills = [skill.lower() for skill in requirement.get("skills", []) if skill]
        combined = " ".join(ref["statement"].lower() for ref in selected)
        strong_supported = bool(skills) and all(skill in combined for skill in skills)
        match["coverage"] = "strong" if decision.coverage == "strong" and strong_supported else "partial"
        match["evidence"] = selected
        match["reason"] = decision.reason[:300] or match["reason"]
    baseline["missing_req_ids"] = [row["req_id"] for row in baseline["matches"] if row["coverage"] == "none"]
    return baseline
