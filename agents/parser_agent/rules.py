"""Mode A: rule-based field extraction from heading-split sections."""

from __future__ import annotations

import re

from agents.core.schemas import (
    Award, Basic, Education, Experience, Link, ProfileData, Project, TextItem,
)
from agents.parser_agent.layout import Line, Section

_YM = r"(\d{4})\s*[.\-/年]\s*(\d{1,2})\s*月?"
DATE_RANGE = re.compile(
    _YM + r"\s*[-–—~～至到]+\s*(?:" + _YM + r"|(至今|今|现在|present|now))", re.I
)
YEAR_RANGE = re.compile(r"(?<!\d)(\d{4})\s*[-–—~～至到]+\s*(\d{4}|至今|现在|present)(?!\d)", re.I)
SINGLE_DATE = re.compile(r"(\d{4})\s*[.\-/年]\s*(\d{1,2})|(\d{4})\s*年")

BULLET = re.compile(r"^(?:[•·●○■□◆◇▪▶►\-*–—✓√]|\d{1,2}[.、)）])\s*")
PHONE = re.compile(r"(?<!\d)(?:\+?86[-\s]?)?(1[3-9]\d[-\s]?\d{4}[-\s]?\d{4})(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(r"(https?://[^\s，,；;]+|(?:github\.com|gitee\.com)/[^\s，,；;]+)", re.I)
SCHOOL = re.compile(r"大学|学院|学校|university|college|institute", re.I)
DEGREE = re.compile(r"本科|硕士|博士|学士|研究生|专科|大专|bachelor|master|ph\.?d|mba", re.I)
TITLE = re.compile(r"实习|工程师|开发|经理|助理|分析师|研究员|设计|运营|产品|算法|测试|顾问|专员|"
                   r"intern|engineer|developer|analyst|manager", re.I)
TEAM = re.compile(r"部|组|团队|中心|事业群|实验室|lab", re.I)
ROLE = re.compile(r"负责人|组长|队长|成员|核心|owner|leader|主要开发|独立开发", re.I)
BACKGROUND = re.compile(r"^(项目)?(背景|简介|描述|介绍|概述)[:：]")
KEYWORDS = re.compile(r"^(技术栈|技术关键词|关键词|技术|使用技术|技术选型)[:：]")
IMPACT = re.compile(r"\d.*(提升|降低|减少|增长|节省|提高|缩短|优化|达到|覆盖|%|％|倍|万|QPS|TPS)|"
                    r"(提升|降低|减少|增长|节省|提高|缩短).*\d")
PROJECT_HEAD = re.compile(r"^(项目名称|项目)[:：]\s*")
SPLIT = re.compile(r"\s*[|｜]\s*|\s{2,}|\t")
TERMINAL = "。；;！!.…"


def format_dates(text: str) -> tuple[str, str]:
    """Return (normalized dates, text without the date part)."""
    m = DATE_RANGE.search(text)
    if m:
        y1, m1, y2, m2, now = m.groups()
        end = f"{y2}.{int(m2):02d}" if y2 else "至今"
        return f"{y1}.{int(m1):02d}-{end}", (text[:m.start()] + " " + text[m.end():]).strip()
    m = YEAR_RANGE.search(text)
    if m:
        end = m.group(2) if m.group(2).isdigit() else "至今"
        return f"{m.group(1)}-{end}", (text[:m.start()] + " " + text[m.end():]).strip()
    return "", text


def strip_bullet(text: str) -> tuple[str, bool]:
    m = BULLET.match(text)
    if m:
        return text[m.end():].strip(), True
    return text.strip(), False


def tokens(text: str) -> list[str]:
    return [t.strip(" ,，") for t in SPLIT.split(text) if t.strip(" ,，")]


# ---------------------------------------------------------------- basic

def parse_basic(section: Section | None, all_lines: list[Line]) -> Basic:
    basic = Basic()
    lines = section.lines if section else all_lines[:12]
    text = "\n".join(l.text for l in lines)
    blob = "\n".join(l.text for l in all_lines[:40])
    if m := PHONE.search(text) or PHONE.search(blob):
        basic.phone = re.sub(r"[-\s]", "", m.group(1))
    if m := EMAIL.search(text) or EMAIL.search(blob):
        basic.email = m.group(0)
    for url in URL.findall(text):
        label = "GitHub" if "github" in url.lower() else "链接"
        basic.links.append(Link(label=label, url=url if url.startswith("http") else "https://" + url))
    if m := re.search(r"(现居|所在地|所在城市|城市|居住地|地址)[:：]?\s*([一-龥]{2,6})", text):
        basic.city = m.group(2)
    if m := re.search(r"(求职意向|意向岗位|应聘岗位|求职岗位|目标岗位)[:：]?\s*([^|｜\n]{2,30})", text):
        basic.headline = m.group(2).strip()

    candidates = []
    for line in lines:
        t = re.sub(r"^姓\s*名[:：]\s*", "", line.text).strip()
        if re.fullmatch(r"[一-龥·]{2,5}|[A-Za-z][A-Za-z .]{1,24}", t) and not SCHOOL.search(t):
            candidates.append((line.size, -lines.index(line), t))
    if candidates:
        basic.name = max(candidates)[2]
    return basic


# ---------------------------------------------------------------- education

def parse_education(section: Section) -> list[Education]:
    entries: list[Education] = []
    cur: Education | None = None

    def fill_header(edu: Education, rest: str) -> None:
        for tok in tokens(rest):
            if not edu.school and SCHOOL.search(tok):
                edu.school = tok
            elif not edu.degree and DEGREE.search(tok) and len(tok) <= 8:
                edu.degree = tok
            elif not edu.major and len(tok) <= 20 and not re.search(r"GPA|排名|绩点", tok, re.I):
                edu.major = re.sub(r"^专业[:：]", "", tok)

    for line in section.lines:
        text, _ = strip_bullet(line.text)
        dates, rest = format_dates(text)
        if SCHOOL.search(rest) and len(rest) <= 60:
            if cur is None or cur.school:
                cur = Education()
                entries.append(cur)
            fill_header(cur, rest)
            if dates:
                cur.dates = dates
        elif dates and cur is not None and not cur.dates and len(rest) <= 30:
            cur.dates = dates
            fill_header(cur, rest)
        elif dates and len(rest) <= 30:
            cur = Education(dates=dates)
            entries.append(cur)
            fill_header(cur, rest)
        else:
            if cur is None:
                cur = Education()
                entries.append(cur)
            cur.bullets.append(TextItem(text=text))
    return entries


# ---------------------------------------------------------------- experience / projects

def _classify_body(project: Project, text: str) -> None:
    if KEYWORDS.match(text):
        value = KEYWORDS.sub("", text)
        project.keywords += [t for t in re.split(r"[,，、/;；\s]+", value) if t]
    elif BACKGROUND.match(text):
        project.background.append(TextItem(text=BACKGROUND.sub("", text).strip()))
    elif IMPACT.search(text):
        project.impact.append(TextItem(text=text))
    else:
        project.responsibilities.append(TextItem(text=text))


def _last_item(project: Project) -> TextItem | None:
    candidates = [lst[-1] for lst in (project.background, project.responsibilities, project.impact) if lst]
    return candidates[-1] if candidates else None


def _body_line(project: Project, line: Line, last: list) -> None:
    text, has_bullet = strip_bullet(line.text)
    if not text:
        return
    prev: TextItem | None = last[0]
    if (not has_bullet and prev is not None and prev.text
            and prev.text[-1] not in TERMINAL and len(prev.text) >= 25
            and not KEYWORDS.match(text) and not BACKGROUND.match(text)):
        prev.text += text          # PDF 换行造成的断句，拼回上一条
        return
    _classify_body(project, text)
    last[0] = _last_item(project)


def _is_project_head(line: Line, text: str, has_bullet: bool) -> bool:
    if PROJECT_HEAD.match(text):
        return True
    return (line.bold and not has_bullet and len(text) <= 40
            and text[-1:] not in TERMINAL and not KEYWORDS.match(text) and not BACKGROUND.match(text))


def parse_experience(section: Section) -> list[Experience]:
    entries: list[Experience] = []
    cur: Experience | None = None
    project: Project | None = None
    last: list = [None]
    for line in section.lines:
        text, has_bullet = strip_bullet(line.text)
        dates, rest = format_dates(text)
        if dates and not has_bullet and len(rest) <= 60:
            cur = Experience(dates=dates)
            entries.append(cur)
            for tok in tokens(rest):
                if not cur.company:
                    cur.company = tok
                elif not cur.title and TITLE.search(tok):
                    cur.title = tok
                elif not cur.team and TEAM.search(tok):
                    cur.team = tok
                elif not cur.title:
                    cur.title = tok
            project, last = None, [None]
            continue
        if cur is None:
            cur = Experience()
            entries.append(cur)
        if _is_project_head(line, text, has_bullet) and (project is None or _last_item(project)):
            project = Project(name=PROJECT_HEAD.sub("", text))
            cur.projects.append(project)
            last = [None]
            continue
        if project is None:
            project = Project()
            cur.projects.append(project)
        _body_line(project, line, last)
    return entries


def parse_projects(section: Section) -> list[Project]:
    projects: list[Project] = []
    project: Project | None = None
    last: list = [None]
    for line in section.lines:
        text, has_bullet = strip_bullet(line.text)
        dates, rest = format_dates(text)
        is_head = (dates and not has_bullet and len(rest) <= 60) or _is_project_head(line, text, has_bullet)
        if is_head and (project is None or _last_item(project) or dates):
            if project is not None and not _last_item(project) and dates and not project.dates:
                project.dates = dates       # 名称行和时间行分开写
                for tok in tokens(rest):
                    if not project.role and ROLE.search(tok):
                        project.role = tok
                    elif not project.name:
                        project.name = tok
                continue
            project = Project(dates=dates)
            projects.append(project)
            for tok in tokens(PROJECT_HEAD.sub("", rest)):
                if not project.name:
                    project.name = tok
                elif not project.role and ROLE.search(tok):
                    project.role = tok
                elif not project.subtitle:
                    project.subtitle = tok
            last = [None]
            continue
        if project is None:
            project = Project()
            projects.append(project)
        _body_line(project, line, last)
    return projects


# ---------------------------------------------------------------- skills / awards / summary

_SKILL_PREFIX = re.compile(r"^(熟练掌握|熟练使用|熟练|精通|熟悉|了解|掌握|具备|能够|会使用|擅长)\s*")


def parse_skills(section: Section) -> list[str]:
    skills: list[str] = []
    for line in section.lines:
        text, _ = strip_bullet(line.text)
        if re.search(r"[:：]", text[:12]):
            text = re.split(r"[:：]", text, maxsplit=1)[1]
        for tok in re.split(r"[,，、;；/|｜]+|\s{2,}", text):
            tok = _SKILL_PREFIX.sub("", tok.strip(" 。.")).strip()
            if tok and len(tok) <= 25 and tok not in skills:
                skills.append(tok)
    return skills


def parse_awards(section: Section) -> list[Award]:
    awards: list[Award] = []
    for line in section.lines:
        text, _ = strip_bullet(line.text)
        m = SINGLE_DATE.search(text)
        date = ""
        if m:
            date = f"{m.group(1)}.{int(m.group(2)):02d}" if m.group(1) else m.group(3)
            text = (text[:m.start()] + text[m.end():]).strip(" ,，|｜年月")
        if text:
            awards.append(Award(name=text, date=date))
    return awards


def parse_by_rules(sections: list[Section], all_lines: list[Line]) -> ProfileData:
    profile = ProfileData()
    basic_section = next((s for s in sections if s.type == "basic"), None)
    profile.basic = parse_basic(basic_section, all_lines)
    for section in sections:
        if section.type == "education":
            profile.education += parse_education(section)
        elif section.type == "experience":
            profile.experience += parse_experience(section)
        elif section.type == "projects":
            profile.projects += parse_projects(section)
        elif section.type == "skills":
            profile.skills += [s for s in parse_skills(section) if s not in profile.skills]
        elif section.type == "awards":
            profile.awards += parse_awards(section)
        elif section.type == "summary":
            joined = "".join(strip_bullet(l.text)[0] for l in section.lines)
            profile.basic.summary = (profile.basic.summary + joined).strip()
    return profile
