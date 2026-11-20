"""The only projection from candidate artifacts into the interviewer context."""

from __future__ import annotations

import re

from agents.contracts.interview import InterviewBrief
from backend.app.models import Interview, Job
from backend.app.services.interview_input import interview_job


def project_interview_brief(interview: Interview, job: Job, requirements: list[dict] | None = None) -> InterviewBrief:
    published = interview_job(job)
    if interview.mode == "blind":
        # The recruiter still knows the vacancy title and employer; no hidden evidence data is projected.
        published = {**published, "requirements": [], "responsibilities": [], "keywords": []}
    quotes = []
    if interview.mode == "contrast":
        for req in requirements or []:
            needle = next((term for term in req.get("skills", []) if term and
                           re.search(re.escape(term), interview.resume_text, re.I)), "")
            if not needle:
                continue
            match = re.search(re.escape(needle), interview.resume_text, re.I)
            start, end = max(0, match.start() - 35), min(len(interview.resume_text), match.end() + 35)
            quotes.append({"req_id": req.get("req_id", ""), "requirement": req.get("text", ""),
                           "quote": interview.resume_text[start:end]})
    history = [{"qid": turn.get("qid", ""), "project": turn.get("project", ""),
                "question": turn.get("question", ""), "answer": turn.get("answer", ""),
                "is_follow_up": bool(turn.get("is_follow_up"))} for turn in interview.turns]
    return InterviewBrief(job=published, resume_text=interview.resume_text, history=history,
                          claimed_coverage=quotes, mode=interview.mode)
