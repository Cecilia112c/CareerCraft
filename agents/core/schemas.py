"""Shared data contracts.

ProfileData (用户资料) and ResumeDoc (简历内容) share ONE structure whose field
names match the ASU resume template. Every editable sentence is a TextItem with
a stable id, so selection-polish, sync-back and fact checks all work by id.
"""

from __future__ import annotations

import re
import secrets
import string
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, Iterator

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

_ALPHABET = string.ascii_lowercase + string.digits


def new_id(prefix: str = "i") -> str:
    return prefix + "".join(secrets.choice(_ALPHABET) for _ in range(6))


# ---------------------------------------------------------------- coercion
# LLMs often return null, a bare string or a list of strings. Accept them.

def _to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "；".join(str(v) for v in value if v is not None)
    return str(value).strip()


def _to_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,，、;；|/\n]+", value)
        return [p.strip() for p in parts if p.strip()]
    return [str(v).strip() for v in value if v is not None and str(v).strip()]


def _to_items(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, (str, dict)):
        value = [value]
    out: list = []
    for item in value:
        if isinstance(item, str):
            if item.strip():
                out.append({"text": item.strip()})
        elif isinstance(item, dict):
            item = dict(item)
            if not item.get("id"):
                item.pop("id", None)
            out.append(item)
        else:
            out.append(item)
    return out


def _to_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return list(value)


def _to_dict(value: Any) -> Any:
    return {} if value is None else value


Str = Annotated[str, BeforeValidator(_to_str)]
StrList = Annotated[list[str], BeforeValidator(_to_str_list)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class TextItem(_Model):
    id: str = Field(default_factory=lambda: new_id("b"))
    text: Str = ""
    evidence_ids: list[str] = Field(default_factory=list)


TextList = Annotated[list[TextItem], BeforeValidator(_to_items)]


class Link(_Model):
    label: Str = ""
    url: Str = ""


class Basic(_Model):
    name: Str = ""
    phone: Str = ""
    email: Str = ""
    city: Str = ""
    headline: Str = ""
    summary: Str = ""
    headline_evidence_ids: list[str] = Field(default_factory=list)
    summary_evidence_ids: list[str] = Field(default_factory=list)
    links: Annotated[list[Link], BeforeValidator(_to_list)] = Field(default_factory=list)


class Education(_Model):
    id: str = Field(default_factory=lambda: new_id("e"))
    school: Str = ""
    major: Str = ""
    degree: Str = ""
    dates: Str = ""
    bullets: TextList = Field(default_factory=list)


class Project(_Model):
    id: str = Field(default_factory=lambda: new_id("p"))
    name: Str = ""
    subtitle: Str = ""
    role: Str = ""
    url: Str = ""
    dates: Str = ""
    background: TextList = Field(default_factory=list)        # S / T
    responsibilities: TextList = Field(default_factory=list)  # A
    impact: TextList = Field(default_factory=list)            # R
    keywords: StrList = Field(default_factory=list)


class Experience(_Model):
    id: str = Field(default_factory=lambda: new_id("x"))
    company: Str = ""
    team: Str = ""
    title: Str = ""
    dates: Str = ""
    projects: Annotated[list[Project], BeforeValidator(_to_list)] = Field(default_factory=list)


class Award(_Model):
    id: str = Field(default_factory=lambda: new_id("a"))
    name: Str = ""
    date: Str = ""


class ProfileData(_Model):
    basic: Annotated[Basic, BeforeValidator(_to_dict)] = Field(default_factory=Basic)
    education: Annotated[list[Education], BeforeValidator(_to_list)] = Field(default_factory=list)
    experience: Annotated[list[Experience], BeforeValidator(_to_list)] = Field(default_factory=list)
    projects: Annotated[list[Project], BeforeValidator(_to_list)] = Field(default_factory=list)
    skills: StrList = Field(default_factory=list)
    awards: Annotated[list[Award], BeforeValidator(_to_list)] = Field(default_factory=list)


class Presentation(_Model):
    accent_color: Str = "#2f67a7"
    hidden_ids: StrList = Field(default_factory=list)
    photo: Str = ""   # data URL；导出的 HTML 自带证件照


class ResumeDoc(ProfileData):
    target_job_id: int | None = None
    presentation: Annotated[Presentation, BeforeValidator(_to_dict)] = Field(
        default_factory=Presentation
    )


# ---------------------------------------------------------------- jobs

class JobPosting(_Model):
    source_url: Str = ""
    title: Str = ""
    company: Str = ""
    city: Str = ""
    salary: Str = ""
    experience: Str = ""
    education: Str = ""
    published_text: Str = ""
    published_at: date | None = None
    responsibilities: StrList = Field(default_factory=list)
    requirements: StrList = Field(default_factory=list)
    keywords: StrList = Field(default_factory=list)
    summary: Str = ""


class ScoredJob(JobPosting):
    score: int = 0
    matched: StrList = Field(default_factory=list)
    missing: StrList = Field(default_factory=list)
    salary_low: float | None = None      # 月薪区间（K），由 salary.py 解析，None 表示面议/未知
    salary_high: float | None = None
    pref_match: bool = True              # 是否符合求职偏好（期望城市 / 期望薪资）
    pref_notes: StrList = Field(default_factory=list)


# ---------------------------------------------------------------- traversal

HEADLINE_ID = "basic.headline"
SUMMARY_ID = "basic.summary"


@dataclass
class ItemRef:
    id: str
    text: str
    kind: str          # headline | summary | education | background | responsibility | impact
    context: str       # 例如 "实习经历｜字节跳动｜推荐系统优化"
    owner_id: str      # 所属 project / education 的 id；basic 字段为 "basic"


def iter_projects(doc: ProfileData) -> Iterator[tuple[Project, str]]:
    for exp in doc.experience:
        head = "｜".join(x for x in (exp.company, exp.title) if x)
        for project in exp.projects:
            yield project, f"实习/工作经历｜{head}｜{project.name}".strip("｜")
    for project in doc.projects:
        yield project, f"项目经历｜{project.name}"


def iter_items(doc: ProfileData) -> Iterator[ItemRef]:
    yield ItemRef(HEADLINE_ID, doc.basic.headline, "headline", "求职方向", "basic")
    yield ItemRef(SUMMARY_ID, doc.basic.summary, "summary", "个人简介", "basic")
    for edu in doc.education:
        for b in edu.bullets:
            yield ItemRef(b.id, b.text, "education", f"教育经历｜{edu.school}", edu.id)
    for project, ctx in iter_projects(doc):
        for field, kind in (("background", "background"),
                            ("responsibilities", "responsibility"),
                            ("impact", "impact")):
            for b in getattr(project, field):
                yield ItemRef(b.id, b.text, kind, ctx, project.id)


_FIELD_WHITELIST = {
    "basic": {"name", "phone", "email", "city", "headline", "summary"},
    "education": {"school", "major", "degree", "dates"},
    "experience": {"company", "team", "title", "dates"},
    "project": {"name", "subtitle", "role", "dates", "keywords"},
    "award": {"name", "date"},
}


def _entities(doc: ProfileData) -> Iterator[tuple[str, BaseModel]]:
    for edu in doc.education:
        yield "education", edu
    for exp in doc.experience:
        yield "experience", exp
    for project, _ in iter_projects(doc):
        yield "project", project
    for award in doc.awards:
        yield "award", award


def _text_items(doc: ProfileData) -> Iterator[TextItem]:
    for edu in doc.education:
        yield from edu.bullets
    for project, _ in iter_projects(doc):
        for field in ("background", "responsibilities", "impact"):
            yield from getattr(project, field)


def _resolve_field(doc: ProfileData, key: str) -> tuple[BaseModel, str] | None:
    if "." not in key:
        return None
    owner, field = key.rsplit(".", 1)
    if owner == "basic":
        return (doc.basic, field) if field in _FIELD_WHITELIST["basic"] else None
    for kind, entity in _entities(doc):
        if entity.id == owner:
            return (entity, field) if field in _FIELD_WHITELIST[kind] else None
    return None


def get_text(doc: ProfileData, key: str) -> str | None:
    """key = TextItem id | 'basic.summary' | '<entity id>.<field>' | 'skills'."""
    if key == "skills":
        return "、".join(doc.skills)
    for item in _text_items(doc):
        if item.id == key:
            return item.text
    resolved = _resolve_field(doc, key)
    if resolved:
        value = getattr(*resolved)
        return " / ".join(value) if isinstance(value, list) else value
    return None


def set_text(doc: ProfileData, key: str, text: str) -> bool:
    """Mutate doc in place. Returns False when the key does not exist."""
    text = (text or "").strip()
    if key == "skills":
        doc.skills = _to_str_list(text)
        return True
    for item in _text_items(doc):
        if item.id == key:
            item.text = text
            return True
    resolved = _resolve_field(doc, key)
    if not resolved:
        return False
    entity, field = resolved
    if field == "keywords":
        setattr(entity, field, _to_str_list(text))
    else:
        setattr(entity, field, text)
    return True


# backwards-friendly aliases
get_item_text = get_text
set_item_text = set_text


def find_project(doc: ProfileData, project_id: str) -> tuple[Project, str] | None:
    for project, ctx in iter_projects(doc):
        if project.id == project_id:
            return project, ctx
    return None


def project_text(project: Project) -> str:
    parts = [project.name, project.subtitle, project.role, " ".join(project.keywords)]
    for field in ("background", "responsibilities", "impact"):
        parts += [b.text for b in getattr(project, field)]
    return "\n".join(p for p in parts if p)


def full_text(doc: ProfileData) -> str:
    """Everything the candidate wrote — used as the fact reference for checks."""
    b = doc.basic
    parts = [b.name, b.city, b.headline, b.summary, " ".join(doc.skills)]
    for edu in doc.education:
        parts += [edu.school, edu.major, edu.degree, edu.dates] + [x.text for x in edu.bullets]
    for exp in doc.experience:
        parts += [exp.company, exp.team, exp.title, exp.dates]
    for project, _ in iter_projects(doc):
        parts.append(project_text(project))
    parts += [a.name for a in doc.awards]
    return "\n".join(p for p in parts if p)


def doc_to_text(doc: ProfileData) -> str:
    """Plain-text resume (respects hidden ids for ResumeDoc). Used by the interview agent."""
    hidden = set(doc.presentation.hidden_ids) if isinstance(doc, ResumeDoc) else set()
    b = doc.basic
    lines: list[str] = [b.name, b.headline]
    if b.summary:
        lines += ["", "【个人简介】", b.summary]
    if doc.education:
        lines += ["", "【教育经历】"]
        for edu in doc.education:
            if edu.id in hidden:
                continue
            lines.append(" ".join(x for x in (edu.school, edu.major, edu.degree, edu.dates) if x))
            lines += [f"- {x.text}" for x in edu.bullets if x.text and x.id not in hidden]

    def project_lines(p: Project) -> list[str]:
        out = [f"项目：{p.name}" + (f"（{p.role}）" if p.role else "") + (f" {p.dates}" if p.dates else "")]
        for field, label in (("background", "背景"), ("responsibilities", "职责"), ("impact", "成果")):
            for x in getattr(p, field):
                if x.text and x.id not in hidden:
                    out.append(f"- {label}：{x.text}")
        if p.keywords:
            out.append("技术关键词：" + " / ".join(p.keywords))
        return out

    if doc.experience:
        lines += ["", "【实习/工作经历】"]
        for exp in doc.experience:
            if exp.id in hidden:
                continue
            lines.append(" ".join(x for x in (exp.company, exp.team, exp.title, exp.dates) if x))
            for p in exp.projects:
                if p.id not in hidden:
                    lines += project_lines(p)
    projects = [p for p in doc.projects if p.id not in hidden]
    if projects:
        lines += ["", "【项目经历】"]
        for p in projects:
            lines += project_lines(p)
    if doc.skills:
        lines += ["", "【专业技能】", "、".join(doc.skills)]
    if doc.awards:
        lines += ["", "【获奖情况】"] + [f"- {a.name} {a.date}".strip() for a in doc.awards]
    return "\n".join(lines).strip()
