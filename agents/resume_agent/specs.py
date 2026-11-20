"""resume_agent specs.

  resume.rewrite_project  每个项目一次 STAR 改写（读长期偏好，不用工具）
  resume.headline         求职方向 + 个人简介
  resume.polish           按用户指令局部修改：工作记忆 + 长期偏好 + 工具（读 JD、查/记偏好）
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from agents.core.schemas import Str, StrList, TextList
from agents.harness import AgentSpec, Budget, ContextContract, MemoryPolicy

PROMPTS = Path(__file__).parent / "prompts"
READ_PREFS = MemoryPolicy(read_namespaces=("global", "resume"))


class ProjectRewrite(BaseModel):
    background: TextList = Field(default_factory=list)
    responsibilities: TextList = Field(default_factory=list)
    impact: TextList = Field(default_factory=list)
    keywords: StrList = Field(default_factory=list)


class HeadlineOut(BaseModel):
    headline: Str = ""
    summary: Str = ""


class PatchOut(BaseModel):
    id: Str = ""
    new_text: Str = ""
    reason: Str = ""
    evidence_ids: StrList = Field(default_factory=list)


class PolishLLMOut(BaseModel):
    patches: list[PatchOut] = Field(default_factory=list)
    needs_confirmation: StrList = Field(default_factory=list)


class MatchDecision(BaseModel):
    req_id: str
    coverage: str = "partial"
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class MatchLLMOut(BaseModel):
    matches: list[MatchDecision] = Field(default_factory=list)


def _ids_in_scope(out: PolishLLMOut, req) -> list[str]:
    allowed = {s["id"] for s in req.materials.get("selected", [])}
    bad = [p.id for p in out.patches if p.id not in allowed]
    return [f"patches 里的 id 不在修改范围内：{bad[:5]}，只能使用 <data:selected> 中的 id"] if bad else []


def _summarize_polish(out: PolishLLMOut) -> str:
    if not out.patches:
        return "没有给出修改" + (f"；需要用户补充：{'；'.join(out.needs_confirmation[:2])}" if out.needs_confirmation else "")
    head = "；".join(p.new_text[:40] for p in out.patches[:3])
    return f"改写了 {len(out.patches)} 句：{head}"


REWRITE_PROJECT = AgentSpec(
    id="resume.rewrite_project", agent="resume", prompt=PROMPTS / "generate_item.md", output=ProjectRewrite,
    description="按 STAR 法则改写一个项目", tier="strong", skills=("star-writing",), memory=READ_PREFS,
    budget=Budget(max_input_tokens=16000, max_iterations=2, temperature=0.4),
)


MATCH = AgentSpec(
    id="resume.match", agent="resume", prompt=PROMPTS / "match.md", output=MatchLLMOut,
    description="对岗位要求逐条评估已确认依据", tier="strong", memory=READ_PREFS,
    context_contract=ContextContract(allowed_materials=("job_brief", "confirmed_evidence"),
                                     max_input_tokens=16000),
    budget=Budget(max_input_tokens=16000, max_iterations=2, temperature=0.1),
)

HEADLINE = AgentSpec(
    id="resume.headline", agent="resume", prompt=PROMPTS / "headline.md", output=HeadlineOut,
    description="撰写求职方向与个人简介", tier="strong", memory=READ_PREFS,
    budget=Budget(max_input_tokens=10000, max_iterations=2, temperature=0.4),
)

POLISH = AgentSpec(
    id="resume.polish", agent="resume", prompt=PROMPTS / "polish.md", output=PolishLLMOut,
    description="按用户指令修改指定的简历内容", tier="strong",
    tools=("get_material", "recall_preferences", "remember_preference", "search_knowledge"),
    skills=("resume-polish", "star-writing"),
    lazy_materials=("job_detail",),
    memory=MemoryPolicy(read_namespaces=("global", "resume"), write_namespaces=("resume",),
                        use_working=True, record_working=True),
    budget=Budget(max_input_tokens=20000, max_iterations=5, max_tool_calls=3, max_repairs=1, temperature=0.5),
    validators=(_ids_in_scope,), summarize=_summarize_polish,
)
