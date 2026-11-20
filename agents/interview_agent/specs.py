"""interview_agent specs — isolation is encoded here, not only in prompts:

  * tools=()                         面试官不能调用任何工具（读不到资料库、JD 打分、简历润色记录）
  * memory namespaces = ("interview",)  只能读写面试自己的记忆，读不到 resume / jd 命名空间
  * 工作记忆按面试会话隔离（session = "interview:<id>"）
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

from agents.core.schemas import Str, StrList
from agents.harness import AgentSpec, Budget, MemoryPolicy

PROMPTS = Path(__file__).parent / "prompts"
INTERVIEW_ONLY = MemoryPolicy(read_namespaces=("interview",))


class Coverage(BaseModel):
    requirement: Str = ""
    status: Str = "partial"
    quote: Str = ""


class Issue(BaseModel):
    category: Str = ""
    severity: Str = "medium"
    quote: Str = ""
    problem: Str = ""
    suggestion: Str = ""
    likely_question: Str = ""


class GapReportLLM(BaseModel):
    coverage: list[Coverage] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    strengths: StrList = Field(default_factory=list)


def _to_level(value) -> int:
    digits = re.sub(r"\D", "", str(value or ""))
    return min(max(int(digits[:1] or 1), 1), 3)


class Question(BaseModel):
    qid: Str = ""
    project: Str = ""
    level: Annotated[int, BeforeValidator(_to_level)] = 1
    question: Str = ""
    intent: Str = ""
    anchor: Str = ""
    is_follow_up: bool = False


class QuestionList(BaseModel):
    questions: list[Question] = Field(default_factory=list)


def _to_scores(value) -> dict:
    if not isinstance(value, dict):
        return {}
    out = {}
    for key, v in value.items():
        try:
            out[str(key)] = float(v)
        except (TypeError, ValueError):
            out[str(key)] = 0.0
    return out


class EvaluationLLM(BaseModel):
    scores: Annotated[dict[str, float], BeforeValidator(_to_scores)] = Field(default_factory=dict)
    comment: Str = ""
    strengths: StrList = Field(default_factory=list)
    weaknesses: StrList = Field(default_factory=list)
    follow_up: Str = ""


class FinalReportLLM(BaseModel):
    summary: Str = ""
    risks: StrList = Field(default_factory=list)
    suggestions: StrList = Field(default_factory=list)
    review_topics: StrList = Field(default_factory=list)


def _summarize_eval(out: EvaluationLLM) -> str:
    return f"评价：{out.comment[:60]}" + (f"；追问：{out.follow_up[:40]}" if out.follow_up else "")


DIAGNOSE = AgentSpec(
    id="interview.diagnose", agent="interview", prompt=PROMPTS / "diagnose.md", output=GapReportLLM,
    description="对照 JD 诊断简历不足", tier="strong", memory=INTERVIEW_ONLY,
    budget=Budget(max_input_tokens=20000, max_iterations=2, temperature=0.2),
)

QUESTIONS = AgentSpec(
    id="interview.questions", agent="interview", prompt=PROMPTS / "questions.md", output=QuestionList,
    description="生成项目深挖问题", tier="strong", skills=("interview-deep-dive",), memory=INTERVIEW_ONLY,
    budget=Budget(max_input_tokens=20000, max_iterations=2, temperature=0.5),
)

EVALUATE = AgentSpec(
    id="interview.evaluate", agent="interview", prompt=PROMPTS / "evaluate.md", output=EvaluationLLM,
    description="评价一次作答并给出追问", tier="strong", skills=("interview-deep-dive",),
    memory=MemoryPolicy(read_namespaces=("interview",), use_working=True, record_working=True),
    budget=Budget(max_input_tokens=20000, max_iterations=2, temperature=0.2),
    summarize=_summarize_eval,
)

REPORT = AgentSpec(
    id="interview.report", agent="interview", prompt=PROMPTS / "report.md", output=FinalReportLLM,
    description="汇总面试表现", tier="strong", memory=INTERVIEW_ONLY,
    budget=Budget(max_input_tokens=24000, max_iterations=2, temperature=0.3),
)
