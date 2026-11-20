"""Isolation guard for the interview agent.

The interviewer may only see what a recruiter sees: the JD and the resume text,
plus this session's own Q&A. Any extra field (evidence ids, polish history,
JD-agent notes, ...) makes validation fail -> the agent refuses to run.

This module must NOT import parser_agent / jd_agent / resume_agent
(enforced by tests/test_isolation.py).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

ALLOWED_TOP_LEVEL_KEYS = {"job", "resume_text", "history", "claimed_coverage"}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InterviewJob(_Strict):
    title: str
    company: str = ""
    summary: str = ""
    requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class Turn(_Strict):
    qid: str = ""
    project: str = ""
    question: str
    answer: str
    is_follow_up: bool = False


class ClaimedCoverage(_Strict):
    req_id: str = ""
    requirement: str = ""
    quote: str = ""


class InterviewInput(_Strict):
    job: InterviewJob
    resume_text: str = Field(min_length=20, max_length=20000)
    history: list[Turn] = Field(default_factory=list)
    claimed_coverage: list[ClaimedCoverage] = Field(default_factory=list)


class IsolationError(ValueError):
    pass


def validate_input(raw: dict) -> InterviewInput:
    extra = set(raw) - ALLOWED_TOP_LEVEL_KEYS
    if extra:
        raise IsolationError(f"面试 Agent 只接受 {sorted(ALLOWED_TOP_LEVEL_KEYS)}，收到多余字段：{sorted(extra)}")
    return InterviewInput.model_validate(raw)
