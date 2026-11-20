"""Turn report risks into proposals; never update profile facts directly."""


def propose_requests(report: dict, interview_id: int, job_id: int | None) -> list[dict]:
    proposals = []
    suggestions = report.get("suggestions") or []
    for index, risk in enumerate((report.get("risks") or [])[:10]):
        text = str(risk).strip()
        if not text:
            continue
        proposals.append({"target": {"job_id": job_id, "interview_id": interview_id, "finding": index},
                          "gap_type": "interview_feedback", "question": f"关于“{text}”，你是否有真实经历或材料可以补充？",
                          "priority": "medium", "origin": {"interview_id": interview_id, "risk": text,
                                                          "suggestion": suggestions[index] if index < len(suggestions) else ""},
                          "status": "proposed"})
    return proposals
