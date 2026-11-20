"""jd_agent: search BOSS直聘 postings of the last 3 months (JOB_FRESH_DAYS, default 90),
normalize them, and score them against the candidate profile + job preferences.

Pipeline: template queries -> search API -> dedup -> (optional detail fetch)
-> LLM normalize -> deterministic freshness filter -> deterministic score.
"""

from __future__ import annotations

import os
import re
from datetime import date
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field

from agents.core.runner import Report, noop_report, parallel_map
from agents.core.schemas import ProfileData, ScoredJob, StrList, full_text, iter_projects
from agents.harness import ExecutionContext, invoke
from agents.jd_agent.freshness import fresh_days, is_fresh, parse_published
from agents.jd_agent.salary import format_k, parse_salary
from agents.jd_agent.search_api import SearchError, SearchHit, fetch_page_text, web_search
from agents.jd_agent.specs import NORMALIZE, JobExtract  # noqa: F401  (JobExtract re-exported)

JOB_SITES = ("zhipin.com", "liepin.com", "lagou.com", "51job.com", "zhaopin.com", "shixiseng.com")


class JobGoal(BaseModel):
    """目标岗位 + 求职偏好。薪资单位：月薪 K，0 表示不限。"""
    titles: StrList = Field(default_factory=list)
    cities: StrList = Field(default_factory=list)
    salary_min: float = 0
    salary_max: float = 0


class JobSearchOutput(BaseModel):
    queries: list[str] = Field(default_factory=list)
    jobs: list[ScoredJob] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- scoring (pure code)

def _bigrams(text: str) -> set[str]:
    text = re.sub(r"\s+", "", text.lower())
    return {text[i:i + 2] for i in range(len(text) - 1)} or ({text} if text else set())


def score_job(job: ScoredJob, profile: ProfileData, goal: JobGoal | None = None) -> ScoredJob:
    blob = full_text(profile).lower()
    keywords = list(dict.fromkeys(k for k in job.keywords if k.strip()))[:15]
    if not keywords:
        req = " ".join(job.requirements)
        keywords = list(dict.fromkeys(re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{1,20}", req)))[:15]
    matched = [k for k in keywords if k.lower() in blob]
    coverage = len(matched) / len(keywords) if keywords else 0.5

    title_score = 0.0
    if goal and goal.titles:
        jt = _bigrams(job.title)
        for t in goal.titles:
            bt = _bigrams(t)
            if bt:
                title_score = max(title_score, len(bt & jt) / len(bt))
    else:
        title_score = 0.5
    city_score, salary_score = check_preference(job, goal)

    # 能力匹配 60 + 岗位名称 20 + 期望城市 10 + 期望薪资 10
    job.score = round(coverage * 60 + min(title_score, 1.0) * 20 + city_score * 10 + salary_score * 10)
    job.matched = matched
    job.missing = [k for k in keywords if k not in matched][:8]
    return job


def check_preference(job: ScoredJob, goal: JobGoal | None) -> tuple[float, float]:
    """按期望城市、期望薪资判断是否符合偏好。
    明确不符合 → pref_match=False（每日推送会跳过）；信息缺失 → 视为可能符合，并在 pref_notes 里注明。
    返回 (城市得分, 薪资得分)，各 0~1。"""
    notes: list[str] = []
    ok = True
    rng = parse_salary(job.salary)
    job.salary_low, job.salary_high = (rng if rng else (None, None))

    city_score = 1.0
    if goal and goal.cities:
        if not job.city:
            city_score = 0.5
            notes.append("城市未知")
        elif any(c in job.city or job.city in c for c in goal.cities):
            notes.append(f"城市符合：{job.city}")
        else:
            city_score, ok = 0.0, False
            notes.append(f"城市不符：{job.city}")

    salary_score = 1.0
    lo_want = goal.salary_min if goal else 0
    hi_want = goal.salary_max if goal else 0
    if lo_want or hi_want:
        if rng is None:
            salary_score = 0.5
            notes.append("薪资面议/未知")
        else:
            lo, hi = rng
            too_low = bool(lo_want) and hi < lo_want
            too_high = bool(hi_want) and lo > hi_want
            if too_low or too_high:
                salary_score, ok = 0.0, False
                notes.append(f"薪资不符：约 {format_k(lo, hi)}/月")
            else:
                notes.append(f"薪资符合：约 {format_k(lo, hi)}/月")
    job.pref_match = ok
    job.pref_notes = notes
    return city_score, salary_score


def candidate_skills(profile: ProfileData) -> list[str]:
    skills = list(profile.skills)
    for project, _ in iter_projects(profile):
        skills += [k for k in project.keywords if k not in skills]
    return skills


# ---------------------------------------------------------------- pipeline

def _normalize_url(url: str) -> str:
    parts = urlsplit(url)
    query = "" if "job_detail" in parts.path else parts.query
    return urlunsplit((parts.scheme or "https", parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def build_queries(goal: JobGoal) -> list[str]:
    titles = goal.titles[:3] or ["实习"]
    cities = goal.cities[:2] or [""]
    return [f"BOSS直聘 {t} {c} 招聘".replace("  ", " ") for t in titles for c in cities][:6]


def _extract(title: str, url: str, content: str, ctx: ExecutionContext | None = None) -> JobExtract:
    return invoke(NORMALIZE, variables={"hit_title": title or "(无)", "hit_url": url or "(用户粘贴)"},
                  materials={"job_page": content[:5000]}, ctx=ctx).output


def _to_job(ext: JobExtract, url: str, fallback_date: str = "") -> ScoredJob:
    job = ScoredJob(**ext.model_dump(exclude={"is_job_page"}), source_url=url)
    job.published_text = job.published_text or fallback_date
    job.published_at = parse_published(job.published_text)
    return job


def normalize_text(text: str, url: str = "", profile: ProfileData | None = None,
                   goal: JobGoal | None = None, report: Report = noop_report,
                   ctx: ExecutionContext | None = None) -> ScoredJob:
    """User pasted a JD (and optionally its link)."""
    report(20, "解析 JD")
    ext = _extract("用户粘贴的岗位描述", url, text, ctx)
    job = _to_job(ext, url)
    if not job.title:
        job.title = "未命名岗位"
    report(90, "计算匹配度")
    return score_job(job, profile or ProfileData(), goal)


def search_jobs(goal: JobGoal, profile: ProfileData, report: Report = noop_report,
                max_jobs: int = 12, days: int | None = None) -> JobSearchOutput:
    days = days or fresh_days()          # 默认近 3 个月（JOB_FRESH_DAYS=90）
    out = JobSearchOutput(queries=build_queries(goal))
    stats = {"hits": 0, "deduped": 0, "not_job": 0, "stale": 0, "unknown_date": 0, "failed": 0}

    hits: dict[str, SearchHit] = {}
    for i, query in enumerate(out.queries):
        report(5 + int(30 * i / max(len(out.queries), 1)), f"搜索 {i + 1}/{len(out.queries)}：{query}")
        try:
            for hit in web_search(query, count=20, days=days):
                if hit.url:
                    stats["hits"] += 1
                    hits.setdefault(_normalize_url(hit.url), hit)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)[:200]
            if msg not in out.warnings:
                out.warnings.append(msg)
            if isinstance(exc, SearchError) and re.search(r"Key|余额|未配置", msg):
                break                      # Key 无效 / 余额不足：后面的查询也会失败，直接停止
    if not hits and out.warnings:
        raise SearchError("；".join(out.warnings))
    stats["deduped"] = len(hits)

    boss = {u: h for u, h in hits.items() if "zhipin.com" in u}
    pool = boss or {u: h for u, h in hits.items() if any(s in u for s in JOB_SITES)}
    if not boss and pool:
        out.warnings.append("未检索到 BOSS 直聘链接，已改用其他招聘网站的结果")
    ranked = sorted(pool.items(), key=lambda kv: ("job_detail" not in kv[0], kv[0]))[:max_jobs]
    fetch_detail = os.getenv("JD_FETCH_DETAIL", "0") == "1"
    if fetch_detail and boss and os.getenv("BOSS_USERNAME") and os.getenv("BOSS_PASSWORD"):
        out.warnings.append("BOSS 账号已配置；当前详情抓取不会自动登录，遇到登录或验证码页面会退回搜索摘要")
    done = [0]

    def work(item: tuple[str, SearchHit]):
        url, hit = item
        content = f"标题：{hit.title}\n摘要：{hit.snippet}"
        if fetch_detail:
            page = fetch_page_text(url)
            if page:
                content += "\n页面正文：" + page
        try:
            ext = _extract(hit.title, url, content)
            result = ext, None
        except Exception as exc:  # noqa: BLE001
            result = None, str(exc)
        done[0] += 1
        report(35 + int(55 * done[0] / max(len(ranked), 1)), f"解析岗位 {done[0]}/{len(ranked)}")
        return url, hit, result

    today = date.today()
    for url, hit, (ext, error) in parallel_map(work, ranked, workers=4):
        if ext is None:
            stats["failed"] += 1
            continue
        if not ext.is_job_page or not ext.title:
            stats["not_job"] += 1
            continue
        job = _to_job(ext, url, hit.date_text)
        fresh = is_fresh(job.published_at, days=days, today=today)
        if fresh is False:
            stats["stale"] += 1
            continue
        if fresh is None:
            stats["unknown_date"] += 1
        out.jobs.append(score_job(job, profile, goal))

    report(95, "排序")
    out.jobs.sort(key=lambda j: (j.published_at is not None, j.score), reverse=True)
    out.stats = stats
    return out
