"""resume_agent: STAR generation per project + instruction-driven local edits.

All model calls go through the harness (agents.harness.invoke) with the specs in specs.py.
Every rewritten sentence still passes check_text(): new numbers / tech terms that are not in the
candidate's own material are rejected and the original is kept.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.core.runner import Report, noop_report, parallel_map
from agents.core.schemas import (
    HEADLINE_ID, SUMMARY_ID, JobPosting, ProfileData, Project, ResumeDoc, TextItem,
    _text_items, find_project, full_text, iter_items, iter_projects, project_text,
)
from agents.harness import ExecutionContext, invoke
from agents.harness.context.prompts import data_block
from agents.resume_agent.check import check_text
from agents.resume_agent.grounding import verify_grounded
from agents.resume_agent.specs import (  # noqa: F401  (models re-exported for callers/tests)
    HEADLINE, POLISH, REWRITE_PROJECT, HeadlineOut, PatchOut, PolishLLMOut, ProjectRewrite,
)

MAX_VISIBLE_PROJECTS = 3
MAX_POLISH_ITEMS = 30

# 快捷按钮（可选）：给指令补充一个明确的方向；用户自己写的指令始终优先
POLISH_MODES = {
    "polish": "润色：让表达更专业、流畅、有力，不改变事实。",
    "star": "STAR 化：补齐“背景/目标 → 我的动作与技术方案 → 可验证结果”的逻辑链，动作动词开头。",
    "concise": "精简：在不丢失关键信息（技术、数字、职责）的前提下缩短到原来的 60%~80%。",
    "align_jd": "贴合 JD：用目标岗位的关键词和表达方式改写已有事实，突出与岗位要求相关的部分。",
    "quantify": "突出成果：把已有的结果、数字和交付物前置并写清楚；原文没有的数字放进 needs_confirmation。",
    "custom": "（无快捷方式，完全按用户指令）",
}


class GenerateOutput(BaseModel):
    resume: ResumeDoc
    warnings: list[str] = Field(default_factory=list)


class Patch(BaseModel):
    id: str
    old: str
    new: str
    context: str = ""
    reason: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class PolishOutput(BaseModel):
    patches: list[Patch] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)
    needs_confirmation: list[str] = Field(default_factory=list)
    memory_events: list[dict] = Field(default_factory=list)
    scope: list[str] = Field(default_factory=list)


def job_brief(job: JobPosting | None) -> dict:
    if job is None:
        return {"title": "通用岗位（未指定 JD）"}
    return {"title": job.title, "company": job.company, "summary": job.summary,
            "requirements": job.requirements[:12], "responsibilities": job.responsibilities[:8],
            "keywords": job.keywords[:15]}


def _relevance(project: Project, job: JobPosting | None) -> int:
    if job is None:
        return 0
    text = project_text(project).lower()
    terms = job.keywords + [w for r in job.requirements for w in r.split()]
    return sum(1 for k in set(terms) if len(k) >= 2 and k.lower() in text)


# ---------------------------------------------------------------- generate

def _rewrite_project(project: Project, context: str, job: JobPosting | None, skills: list[str],
                     ctx: ExecutionContext | None, confirmed_evidence: list[dict] | None = None) -> tuple[Project, list[str]]:
    """Return a NEW project object with rewritten items, plus warnings."""
    original = project.model_copy(deep=True)
    if not project_text(project).strip() or not any(
            getattr(project, f) for f in ("background", "responsibilities", "impact")):
        return original, []
    source = {
        "name": project.name, "role": project.role, "keywords": project.keywords,
        "background": [i.model_dump() for i in project.background],
        "responsibilities": [i.model_dump() for i in project.responsibilities],
        "impact": [i.model_dump() for i in project.impact],
    }
    evidence_by_id = {item["id"]: item["statement"] for item in (confirmed_evidence or [])}
    materials = {"project": source}
    if evidence_by_id:
        materials["confirmed_evidence"] = confirmed_evidence
    out: ProjectRewrite = invoke(REWRITE_PROJECT, variables={"context": context,
                                                              "job": data_block("job", job_brief(job))},
                                 materials=materials, ctx=ctx).output
    reference = project_text(project)
    original_text = {i.id: i.text for f in ("background", "responsibilities", "impact")
                     for i in getattr(project, f)}
    source_ids = [f"profile:{key}" for key in original_text]
    grounded = {**{f"profile:{key}": {"statement": value, "level": "L1"}
                   for key, value in original_text.items()},
                **{key: {"statement": value, "level": "L1"} for key, value in evidence_by_id.items()}}
    warnings: list[str] = []
    used: set[str] = set()
    rewritten = original.model_copy(deep=True)
    for field in ("background", "responsibilities", "impact"):
        items: list[TextItem] = []
        for item in getattr(out, field):
            if item.id not in original_text or item.id in used:
                item = TextItem(text=item.text, evidence_ids=item.evidence_ids)  # 新拆分出的句子，生成新 id
            cited_ids = [key for key in item.evidence_ids if key in evidence_by_id]
            problems = (["引用了未经确认的事实"] if len(cited_ids) != len(item.evidence_ids)
                        else verify_grounded(item.text, [*source_ids, *cited_ids], grounded))
            if problems:
                if item.id in original_text:
                    warnings.append(f"「{project.name or context}」有一句改写{problems[0]}，已保留原文")
                    item = TextItem(id=item.id, text=original_text[item.id])
                else:
                    warnings.append(f"「{project.name or context}」丢弃一句新增内容：{problems[0]}")
                    continue
            item.evidence_ids = list(dict.fromkeys([*source_ids, *cited_ids]))
            used.add(item.id)
            items.append(item)
        setattr(rewritten, field, items)
    if not (rewritten.responsibilities or rewritten.impact):
        warnings.append(f"「{project.name or context}」改写结果为空，已保留原文")
        return original, warnings
    allowed = reference.lower()
    keywords = [k for k in out.keywords if k.lower() in allowed]
    if keywords:
        rewritten.keywords = keywords
    return rewritten, warnings


def generate_resume(profile: ProfileData, job: JobPosting | None, job_id: int | None = None,
                    report: Report = noop_report, ctx: ExecutionContext | None = None,
                    confirmed_evidence: list[dict] | None = None) -> GenerateOutput:
    doc = ResumeDoc(**profile.model_copy(deep=True).model_dump(), target_job_id=job_id)
    for item in _text_items(doc):
        if item.text.strip() and not item.evidence_ids:
            item.evidence_ids = [f"profile:{item.id}"]
    basic_refs = [f"profile:{item.id}" for item in _text_items(profile) if item.text.strip()]
    if profile.basic.headline:
        basic_refs.append("profile:basic.headline")
    if profile.basic.summary:
        basic_refs.append("profile:basic.summary")
    if profile.skills:
        basic_refs.append("profile:skills")
    if doc.basic.headline:
        doc.basic.headline_evidence_ids = list(dict.fromkeys(basic_refs))
    if doc.basic.summary:
        doc.basic.summary_evidence_ids = list(dict.fromkeys(basic_refs))
    warnings: list[str] = []

    # 1) 独立项目按与 JD 的相关度排序，只展示前 3 个
    doc.projects.sort(key=lambda p: _relevance(p, job), reverse=True)
    for p in doc.projects[MAX_VISIBLE_PROJECTS:]:
        doc.presentation.hidden_ids.append(p.id)
    visible = [(p, c) for p, c in iter_projects(doc) if p.id not in doc.presentation.hidden_ids]
    report(10, f"规划完成，将润色 {len(visible)} 个项目")

    # 2) 每个项目一次模型调用（并行）
    done = [0]

    def work(item: tuple[Project, str]):
        project, context = item
        try:
            relevant = [item for item in (confirmed_evidence or []) if item.get("project_id") == project.id]
            result = _rewrite_project(project, context, job, profile.skills, ctx, relevant)
        except Exception as exc:  # noqa: BLE001
            result = (project.model_copy(deep=True), [f"「{project.name or context}」润色失败，保留原文：{str(exc)[:60]}"])
        done[0] += 1
        report(10 + int(70 * done[0] / max(len(visible), 1)), f"润色项目 {done[0]}/{len(visible)}")
        return project.id, result

    rewritten = dict(parallel_map(work, visible, workers=4))
    for exp in doc.experience:
        exp.projects = [rewritten.get(p.id, (p, []))[0] for p in exp.projects]
    doc.projects = [rewritten.get(p.id, (p, []))[0] for p in doc.projects]
    for _, warns in rewritten.values():
        warnings += warns

    # 3) headline + summary
    report(85, "撰写求职方向与个人简介")
    brief = {
        "headline": profile.basic.headline, "summary": profile.basic.summary, "skills": profile.skills,
        "education": [f"{e.school} {e.major} {e.degree}" for e in profile.education],
        "experience": [f"{x.company} {x.title}" for x in profile.experience],
        "projects": [p.name for p, _ in iter_projects(profile)],
    }
    try:
        head: HeadlineOut = invoke(HEADLINE, variables={"job": data_block("job", job_brief(job))},
                                   materials={"profile_brief": brief}, ctx=ctx).output
        reference = full_text(profile) + "\n" + (job.title if job else "")
        if head.headline and not check_text(head.headline, reference):
            if not verify_grounded(head.headline, basic_refs, _profile_grounding(profile)):
                doc.basic.headline = head.headline
        if head.summary:
            problems = check_text(head.summary, reference)
            if problems:
                warnings.append(f"个人简介{problems[0]}，已保留原文")
            elif not verify_grounded(head.summary, basic_refs, _profile_grounding(profile)):
                doc.basic.summary = head.summary
            else:
                warnings.append("个人简介缺少可引用的已确认依据，已保留原文")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"个人简介生成失败：{str(exc)[:60]}")
    report(95, "完成")
    return GenerateOutput(resume=doc, warnings=warnings)


def _profile_grounding(profile: ProfileData) -> dict[str, dict]:
    evidence = {f"profile:{item.id}": {"statement": item.text, "level": "L1"}
                for item in _text_items(profile)}
    evidence["profile:basic.headline"] = {"statement": profile.basic.headline, "level": "L1"}
    evidence["profile:basic.summary"] = {"statement": profile.basic.summary, "level": "L1"}
    evidence["profile:skills"] = {"statement": "、".join(profile.skills), "level": "L1"}
    return evidence


# ---------------------------------------------------------------- instruction-driven edits

def expand_scope(doc: ResumeDoc, ids: list[str]) -> list[str]:
    """User may point at a sentence id or a whole block (project / experience / education id)."""
    refs = [r for r in iter_items(doc) if r.text.strip()]
    by_id = {r.id: r for r in refs}
    exp_projects = {x.id: {p.id for p in x.projects} for x in doc.experience}
    out: list[str] = []
    for key in dict.fromkeys(ids):
        if key in by_id:
            out.append(key)
        elif key in exp_projects:
            out += [r.id for r in refs if r.owner_id in exp_projects[key]]
        else:                                          # project id / education id
            out += [r.id for r in refs if r.owner_id == key]
    return list(dict.fromkeys(out))[:MAX_POLISH_ITEMS]


def polish_selection(doc: ResumeDoc, profile: ProfileData, ids: list[str], mode: str, instruction: str,
                     job: JobPosting | None, report: Report = noop_report, ctx: ExecutionContext | None = None,
                     scope_label: str = "", confirmed_evidence: list[dict] | None = None) -> PolishOutput:
    refs = {r.id: r for r in iter_items(doc)}
    scope = expand_scope(doc, ids)
    selected = [refs[i] for i in scope]
    if not selected:
        return PolishOutput(rejected=["没有可修改的句子（请点选项目、经历、个人简介等正文模块，或选中具体句子）"])
    report(15, f"修改 {len(selected)} 句")

    profile_blob = full_text(profile)
    payload = []
    facts_by_id: dict[str, str] = {}
    for ref in selected:
        found = find_project(doc, ref.owner_id)
        facts = project_text(found[0]) if found else ""
        if ref.id in (HEADLINE_ID, SUMMARY_ID) or not facts:
            facts = profile_blob[:3000]
        facts_by_id[ref.id] = facts + "\n" + profile_blob
        payload.append({"id": ref.id, "text": ref.text, "context": ref.context, "project_facts": facts[:2500]})

    materials: dict = {"selected": payload}
    evidence_by_id = {item["id"]: item["statement"] for item in (confirmed_evidence or [])}
    profile_evidence = _profile_grounding(profile)
    grounded = {**profile_evidence, **{key: {"statement": value, "level": "L1"}
                                     for key, value in evidence_by_id.items()}}
    if evidence_by_id:
        materials["confirmed_evidence"] = [{"id": key, "statement": value} for key, value in evidence_by_id.items()]
    if job is not None:
        materials["job_detail"] = job_brief(job)
    result_inv = invoke(
        POLISH,
        variables={"scope_label": scope_label or f"{len(selected)} 句",
                   "mode_desc": POLISH_MODES.get(mode, POLISH_MODES["custom"]),
                   "job_keywords": ("关键词：" + ", ".join(job.keywords[:15])) if job else "（未指定目标岗位）"},
        materials=materials,
        instruction=instruction.strip() or POLISH_MODES.get(mode, POLISH_MODES["polish"]),
        ctx=ctx,
    )
    out: PolishLLMOut = result_inv.output
    report(85, "校验改写内容")
    result = PolishOutput(needs_confirmation=list(out.needs_confirmation),
                          memory_events=result_inv.memory_events, scope=scope)
    wanted = {r.id: r for r in selected}
    seen: set[str] = set()
    for patch in out.patches:
        ref = wanted.get(patch.id)
        if ref is None or patch.id in seen:
            continue
        seen.add(patch.id)
        new = patch.new_text.strip()
        # Ignore formatting-only rewrites; they do not help the user improve a resume.
        meaningful = lambda value: "".join(ch for ch in value if ch.isalnum())
        if not new or meaningful(new) == meaningful(ref.text):
            continue
        unknown_ids = set(patch.evidence_ids) - set(evidence_by_id)
        if unknown_ids:
            result.rejected.append(f"「{ref.text[:20]}…」引用了未经确认的依据，已拦截")
            continue
        source_ids = [key for key in profile_evidence if key == f"profile:{ref.id}"]
        if ref.id in (HEADLINE_ID, SUMMARY_ID):
            source_ids = [key for key, fact in profile_evidence.items() if fact["statement"].strip()]
        found = find_project(profile, ref.owner_id)
        if found:
            source_ids = [f"profile:{item.id}" for field in ("background", "responsibilities", "impact")
                          for item in getattr(found[0], field) if f"profile:{item.id}" in profile_evidence]
        cited_ids = list(dict.fromkeys([*source_ids, *patch.evidence_ids]))
        problems = verify_grounded(new, cited_ids, grounded)
        if problems:
            result.rejected.append(f"「{ref.text[:20]}…」的改写{problems[0]}，已拦截")
            continue
        result.patches.append(Patch(id=ref.id, old=ref.text, new=new, context=ref.context,
                                    reason=patch.reason, evidence_ids=cited_ids))
    return result
