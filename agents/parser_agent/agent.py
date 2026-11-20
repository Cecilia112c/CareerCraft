"""parser_agent: PDF -> ProfileData suggestions.

mode="rule": heading detection + regex rules, no LLM, ~1s.
mode="llm" : same sections, then each section is extracted by the LLM in parallel;
             a failed section falls back to the rule result.
The result is only a suggestion; the user confirms before it is saved.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.core.runner import Report, noop_report, parallel_map
from agents.core.schemas import ProfileData
from agents.harness import ExecutionContext, invoke
from agents.parser_agent.layout import Line, Section, extract_lines, lines_from_text, split_sections
from agents.parser_agent.rules import parse_by_rules
from agents.parser_agent.specs import EXTRACT_SECTION

_TARGETS = {
    "basic": "basic（name/phone/email/city/headline/summary/links）",
    "education": "education",
    "experience": "experience（含 projects）",
    "projects": "projects",
    "skills": "skills",
    "awards": "awards",
    "summary": "basic.summary",
    "all": "全部字段（basic、education、experience、projects、skills、awards）",
}


class SectionInfo(BaseModel):
    type: str
    title: str
    text: str


class ParseResult(BaseModel):
    mode: str
    sections: list[SectionInfo] = Field(default_factory=list)
    profile: ProfileData = Field(default_factory=ProfileData)
    unparsed: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    text: str = ""


def _merge_section(target: ProfileData, part: ProfileData, kind: str) -> None:
    if kind == "basic":
        for field in ("name", "phone", "email", "city", "headline", "summary"):
            value = getattr(part.basic, field)
            if value and not getattr(target.basic, field):
                setattr(target.basic, field, value)
        if part.basic.links and not target.basic.links:
            target.basic.links = part.basic.links
        if part.skills:
            target.skills += [s for s in part.skills if s not in target.skills]
    elif kind == "summary":
        target.basic.summary = (target.basic.summary + part.basic.summary).strip()
    elif kind == "skills":
        target.skills += [s for s in part.skills if s not in target.skills]
    elif kind in ("education", "experience", "projects", "awards"):
        getattr(target, kind).extend(getattr(part, kind))


def _llm_section(section: Section, ctx: ExecutionContext | None) -> ProfileData:
    return invoke(
        EXTRACT_SECTION,
        variables={"section_type": section.type, "section_title": section.title,
                   "target_fields": _TARGETS.get(section.type, "对应字段")},
        materials={"resume_section": section.text[:6000]},
        ctx=ctx,
    ).output


def _parse_lines(lines: list[Line], mode: str, report: Report, ctx: ExecutionContext | None = None) -> ParseResult:
    report(15, "识别标题与分区")
    sections = split_sections(lines)
    rule_profile = parse_by_rules(sections, lines)
    result = ParseResult(
        mode=mode,
        sections=[SectionInfo(type=s.type, title=s.title, text=s.text) for s in sections],
        unparsed=[s.text for s in sections if s.type == "other" and s.text],
        text="\n".join(l.text for l in lines),
    )
    if mode != "llm":
        result.profile = rule_profile
        report(95, "规则识别完成")
        return result

    targets = [s for s in sections if s.type in _TARGETS and s.text.strip()]
    if len(targets) <= 1:   # 没识别出标题：整份交给模型
        targets = [Section(type="all", title="全文", lines=lines)]
    report(25, f"AI 抽取中（{len(targets)} 个分区）")

    def work(section: Section):
        try:
            return section, _llm_section(section, ctx), None
        except Exception as exc:  # noqa: BLE001
            return section, None, str(exc)

    merged = ProfileData()
    for section, part, error in parallel_map(work, targets, workers=4):
        if part is None:
            result.warnings.append(f"「{section.title}」AI 抽取失败，已使用规则结果：{error[:80]}")
            continue
        if section.type == "all":
            merged = part
        else:
            _merge_section(merged, part, section.type)
    # 规则结果兜底：AI 漏掉的分区或基本字段
    for kind in ("education", "experience", "projects", "awards"):
        if not getattr(merged, kind):
            setattr(merged, kind, getattr(rule_profile, kind))
    if not merged.skills:
        merged.skills = rule_profile.skills
    for field in ("name", "phone", "email", "city", "headline", "summary"):
        if not getattr(merged.basic, field):
            setattr(merged.basic, field, getattr(rule_profile.basic, field))
    if not merged.basic.links:
        merged.basic.links = rule_profile.basic.links
    result.profile = merged
    report(95, "AI 抽取完成")
    return result


def parse_pdf(pdf_bytes: bytes, mode: str = "rule", report: Report = noop_report,
              ctx: ExecutionContext | None = None) -> ParseResult:
    report(5, "读取 PDF 版面")
    lines = extract_lines(pdf_bytes)
    if not lines:
        return ParseResult(mode=mode, warnings=["PDF 中没有可提取的文字（可能是扫描件），请手动填写"])
    return _parse_lines(lines, mode, report, ctx)


def parse_text(text: str, mode: str = "rule", report: Report = noop_report,
               ctx: ExecutionContext | None = None) -> ParseResult:
    return _parse_lines(lines_from_text(text), mode, report, ctx)
