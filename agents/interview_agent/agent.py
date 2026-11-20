"""interview_agent: diagnose resume gaps, deep-dive questions, evaluate answers, report.

Isolated by design: every public function takes an InterviewInput (validated by
guard.validate_input) and nothing else from other agents. Only agents.core and agents.harness
are imported; the specs give the interviewer no tools and only the "interview" memory namespace.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from pydantic import Field

from agents.core.runner import Report, noop_report
from agents.harness import ExecutionContext, invoke
from agents.harness.context.prompts import data_block
from agents.interview_agent.guard import InterviewInput
from agents.interview_agent.specs import (  # noqa: F401  (models re-exported)
    DIAGNOSE, EVALUATE, QUESTIONS, REPORT, Coverage, EvaluationLLM, FinalReportLLM, GapReportLLM, Issue,
    Question, QuestionList,
)

PROMPTS = Path(__file__).parent / "prompts"
DIMENSIONS = ("correctness", "depth", "ownership", "evidence", "consistency")
LEVEL_DESC = {1: "概览题", 2: "技术决策题", 3: "深挖题"}


def _system() -> str:
    return (PROMPTS / "system.md").read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _materials(inp: InterviewInput, **extra) -> dict:
    materials = {"job": inp.job.model_dump(), "resume": inp.resume_text, **extra}
    if inp.claimed_coverage:
        materials["claimed_coverage"] = [item.model_dump() for item in inp.claimed_coverage]
    return materials


# ---------------------------------------------------------------- diagnose

class GapReport(GapReportLLM):
    coverage_rate: float = 0.0      # 代码计算
    fit: str = ""                   # 代码计算：strong / moderate / weak


def diagnose(inp: InterviewInput, report: Report = noop_report, ctx: ExecutionContext | None = None) -> GapReport:
    report(10, "对照 JD 诊断简历")
    raw = invoke(DIAGNOSE, variables={"system": _system()}, materials=_materials(inp), ctx=ctx).output
    out = GapReport(**raw.model_dump())
    resume = _norm(inp.resume_text)
    for c in out.coverage:
        c.status = c.status if c.status in ("covered", "partial", "missing") else "partial"
        if c.quote and _norm(c.quote) not in resume:
            c.quote = ""        # 引用不在简历里：不展示，避免“幻觉引用”
    for i in out.issues:
        i.severity = i.severity if i.severity in ("high", "medium", "low") else "medium"
        if i.quote and _norm(i.quote) not in resume:
            i.quote = ""
    order = {"high": 0, "medium": 1, "low": 2}
    out.issues.sort(key=lambda i: order[i.severity])
    if out.coverage:
        score = sum({"covered": 1.0, "partial": 0.5}.get(c.status, 0.0) for c in out.coverage)
        out.coverage_rate = round(score / len(out.coverage), 2)
    highs = sum(1 for i in out.issues if i.severity == "high")
    rate = out.coverage_rate
    out.fit = "strong" if rate >= 0.75 and highs <= 1 else ("moderate" if rate >= 0.5 else "weak")
    return out


# ---------------------------------------------------------------- questions

def plan_questions(inp: InterviewInput, gaps: GapReport | None, total: int = 10,
                   report: Report = noop_report, ctx: ExecutionContext | None = None) -> list[Question]:
    report(55, "生成项目深挖问题")
    gap_brief = [{"category": i.category, "severity": i.severity, "quote": i.quote,
                  "likely_question": i.likely_question} for i in (gaps.issues if gaps else [])][:8]
    out: QuestionList = invoke(QUESTIONS, variables={"system": _system()},
                               materials=_materials(inp, gaps=gap_brief), ctx=ctx).output
    groups: dict[str, list[Question]] = {}
    for q in out.questions:
        if q.question.strip():
            q.is_follow_up = False
            groups.setdefault(q.project or "其他", []).append(q)
    if not groups:
        return []
    per_project = max(2, math.ceil(total / len(groups)))
    picked: list[Question] = []
    for qs in groups.values():
        picked += sorted(qs, key=lambda q: q.level)[:per_project]
    picked = picked[:total]
    for n, q in enumerate(picked, start=1):
        q.qid = f"q{n}"
    return picked


# ---------------------------------------------------------------- evaluate

class Evaluation(EvaluationLLM):
    average: float = 0.0          # 代码计算
    next_action: str = "next"     # 代码决定：follow_up / next


def evaluate_answer(inp: InterviewInput, question: Question, answer: str, follow_ups_so_far: int,
                    report: Report = noop_report, ctx: ExecutionContext | None = None) -> Evaluation:
    report(20, "评价作答")
    history = [t.model_dump(include={"question", "answer"}) for t in inp.history
               if t.project == question.project][-6:]
    raw = invoke(
        EVALUATE,
        variables={"system": _system(),
                   "level_desc": "追问" if question.is_follow_up else LEVEL_DESC.get(question.level, "追问"),
                   "question": question.question, "intent": question.intent or "（无）",
                   "anchor": question.anchor or "（无）",
                   "project_history": data_block("history", history or "（无）")},
        materials=_materials(inp, answer=answer[:4000] or "（候选人未作答）"),
        instruction=f"请评价候选人对“{question.question[:60]}”的作答。",
        ctx=ctx,
    ).output
    out = Evaluation(**raw.model_dump())
    out.scores = {d: float(min(max(round(out.scores.get(d, 0.0)), 0), 4)) for d in DIMENSIONS}
    out.average = round(sum(out.scores.values()) / len(DIMENSIONS), 2)
    # 追问规则由代码决定：答得浅（均分≤2.2）且该题追问不到 2 次
    if not answer.strip():
        out.next_action = "next"
    elif out.average <= 2.2 and follow_ups_so_far < 2 and out.follow_up.strip():
        out.next_action = "follow_up"
    else:
        out.next_action = "next"
    return out


# ---------------------------------------------------------------- report

class FinalReport(FinalReportLLM):
    project_scores: dict[str, dict[str, float]] = Field(default_factory=dict)   # 代码计算
    overall: float = 0.0                                                     # 代码计算


def compute_scores(evaluations: list[tuple[str, dict[str, float]]]) -> tuple[dict, float]:
    buckets: dict[str, list[dict[str, float]]] = {}
    for project, scores in evaluations:
        if scores:
            buckets.setdefault(project or "其他", []).append(scores)
    result: dict[str, dict[str, float]] = {}
    for project, rows in buckets.items():
        result[project] = {d: round(sum(r.get(d, 0) for r in rows) / len(rows), 2) for d in DIMENSIONS}
    all_rows = [r for rows in buckets.values() for r in rows]
    overall = round(sum(sum(r.get(d, 0) for d in DIMENSIONS) / len(DIMENSIONS) for r in all_rows)
                    / len(all_rows), 2) if all_rows else 0.0
    return result, overall


def final_report(inp: InterviewInput, evaluations: list[tuple[str, dict[str, float]]],
                 report: Report = noop_report, ctx: ExecutionContext | None = None) -> FinalReport:
    report(20, "汇总面试表现")
    project_scores, overall = compute_scores(evaluations)
    transcript = [t.model_dump(include={"project", "question", "answer", "is_follow_up"}) for t in inp.history]
    raw = invoke(REPORT, variables={"system": _system(), "scores": {"overall": overall, "projects": project_scores}},
                 materials=_materials(inp, transcript=transcript), ctx=ctx).output
    return FinalReport(**raw.model_dump(), project_scores=project_scores, overall=overall)
