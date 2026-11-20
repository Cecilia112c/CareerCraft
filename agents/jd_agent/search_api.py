"""Search providers (博查 / Tavily) and a polite single-page fetcher.

博查 Web Search API（官方文档：https://open.bocha.cn ，Skill 规范：
https://github.com/Bocha-Labs/bocha-skills/blob/main/bocha-web-search/SKILL.md）
  POST https://api.bocha.cn/v1/web-search      （旧域名 api.bochaai.com 同样可用，作为备用）
  Header: Authorization: Bearer <BOCHA_API_KEY>
  Body:   query(必填) / freshness(noLimit|oneDay|oneWeek|oneMonth|oneYear|YYYY-MM-DD..YYYY-MM-DD)
          / summary / count(1-50)
          include / exclude：限定或排除站点，多个域名用 | 分隔
  返回:   data.webPages.value[]：name / url / snippet / summary / siteName / datePublished
  错误:   400 参数错误 / 401 Key 无效 / 403 余额不足 / 429 频率过高 / 500 服务错误（附 log_id）

合规说明：只使用公开搜索引擎的结果；详情页仅做低频单次访问，
遇到登录页/验证码页立即放弃，不绕过任何防护。

自检：python -m agents.jd_agent.search_api "后端开发实习 深圳"
"""

from __future__ import annotations

import html
import os
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta

import httpx

from agents.jd_agent.freshness import fresh_days

BOCHA_ENDPOINTS = ("https://api.bocha.cn/v1/web-search", "https://api.bochaai.com/v1/web-search")
BOSS_SITE = "zhipin.com"
JOB_SITES = ("zhipin.com", "liepin.com", "lagou.com", "51job.com", "zhaopin.com", "shixiseng.com")

_BOCHA_ERRORS = {
    400: "请求参数错误",
    401: "API Key 无效，请检查 .env 中的 BOCHA_API_KEY",
    403: "博查账户余额不足，请到 open.bocha.cn 充值",
    429: "请求过于频繁，请稍后再试",
    500: "博查服务器错误，请稍后再试",
}


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str
    date_text: str = ""
    site_name: str = ""


class SearchError(RuntimeError):
    pass


# ---------------------------------------------------------------- config

def bocha_key() -> str:
    """官方变量名 BOCHA_API_KEY；兼容旧的 SEARCH_API_KEY。"""
    return (os.getenv("BOCHA_API_KEY") or os.getenv("SEARCH_API_KEY") or "").strip()


def provider() -> str:
    explicit = os.getenv("SEARCH_PROVIDER", "").strip().lower()
    if explicit:
        return explicit
    return "tavily" if os.getenv("TAVILY_API_KEY") and not bocha_key() else "bocha"


# ---------------------------------------------------------------- bocha

def _bocha_request(body: dict) -> dict:
    key = bocha_key()
    if not key:
        raise SearchError("未配置博查 API Key：请在 CareerCraft/.env 中填写 BOCHA_API_KEY")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    endpoints = [os.getenv("BOCHA_API_URL")] if os.getenv("BOCHA_API_URL") else list(BOCHA_ENDPOINTS)
    last_error = ""
    for endpoint in endpoints:
        for attempt in range(3):               # 429 / 5xx / 网络错误：指数退避重试
            try:
                r = httpx.post(endpoint, json=body, headers=headers, timeout=25)
            except httpx.HTTPError as exc:
                last_error = f"网络错误：{exc}"
                time.sleep(0.8 * (attempt + 1))
                continue
            try:
                data = r.json()
            except ValueError:
                data = {}
            code = data.get("code", r.status_code) if isinstance(data, dict) else r.status_code
            try:
                code = int(code)
            except (TypeError, ValueError):
                code = r.status_code
            if r.status_code == 200 and code == 200:
                return data
            status = code if code != 200 else r.status_code
            log_id = data.get("log_id", "") if isinstance(data, dict) else ""
            msg = (data.get("msg") or data.get("message") or "") if isinstance(data, dict) else ""
            last_error = f"{_BOCHA_ERRORS.get(status, f'HTTP {status}')}（{msg or r.text[:80]}；log_id={log_id}）"
            if status in (400, 401, 403):     # 不可重试的错误
                raise SearchError("博查搜索失败：" + last_error)
            if status == 429 or status >= 500:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise SearchError("博查搜索失败：" + last_error)
        # 当前域名重试用尽（多为网络问题），换备用域名
    raise SearchError("博查搜索失败：" + last_error)


def bocha_freshness(days: int | None, today: date | None = None) -> str:
    """博查 freshness：固定档位 oneDay/oneWeek/oneMonth/oneYear，其它天数用日期范围 YYYY-MM-DD..YYYY-MM-DD。"""
    if not days:
        return "noLimit"
    named = {1: "oneDay", 7: "oneWeek", 30: "oneMonth", 365: "oneYear"}
    if days in named:
        return named[days]
    today = today or date.today()
    return f"{(today - timedelta(days=days)).isoformat()}..{today.isoformat()}"


def _bocha(query: str, count: int, days: int | None, include: str = "") -> list[SearchHit]:
    body: dict = {
        "query": query,
        "freshness": bocha_freshness(days),
        "summary": True,
        "count": max(1, min(int(count), 50)),
    }
    if include:
        body["include"] = include
    data = _bocha_request(body)
    values = ((data.get("data") or {}).get("webPages") or {}).get("value") or []
    hits = []
    for v in values:
        if not v.get("url"):
            continue
        hits.append(SearchHit(
            title=v.get("name", "") or "",
            url=v["url"],
            snippet=(v.get("summary") or v.get("snippet") or "")[:3000],
            date_text=v.get("datePublished") or v.get("dateLastCrawled") or "",
            site_name=v.get("siteName", "") or "",
        ))
    return hits


# ---------------------------------------------------------------- tavily (备选)

def _tavily(query: str, count: int, days: int | None, include: str = "") -> list[SearchHit]:
    key = (os.getenv("TAVILY_API_KEY") or os.getenv("SEARCH_API_KEY") or "").strip()
    if not key:
        raise SearchError("未配置 TAVILY_API_KEY")
    body: dict = {"query": query, "max_results": min(count, 20)}
    if include:
        body["include_domains"] = include.split("|")
    if days:   # Tavily 只有 day/week/month/year 四档，取能覆盖窗口的最小档，再由 freshness.py 精确过滤
        body["time_range"] = "day" if days <= 1 else "week" if days <= 7 else "month" if days <= 31 else "year"
    r = httpx.post("https://api.tavily.com/search", json=body, timeout=25,
                   headers={"Authorization": f"Bearer {key}"})
    if r.status_code != 200:
        raise SearchError(f"Tavily 搜索失败 HTTP {r.status_code}: {r.text[:120]}")
    return [SearchHit(title=v.get("title", ""), url=v.get("url", ""), snippet=v.get("content", ""),
                      date_text=v.get("published_date") or "") for v in r.json().get("results", [])
            if v.get("url")]


# ---------------------------------------------------------------- public API

def web_search(query: str, count: int = 20, days: int | None = -1) -> list[SearchHit]:
    """先只搜 BOSS 直聘近 days 天（默认 JOB_FRESH_DAYS=90，即近 3 个月）；没有结果时依次放宽：
    其它招聘网站 → 不限时间（时效最终由 freshness.py 根据页面发布时间再判断）。days=None 表示不限时间。"""
    if days == -1:
        days = fresh_days()
    fn = _tavily if provider() == "tavily" else _bocha
    attempts = [(BOSS_SITE, days), ("|".join(JOB_SITES), days)]
    if days:
        attempts += [(BOSS_SITE, None), ("|".join(JOB_SITES), None)]
    for include, window in attempts:
        hits = fn(query, count, window, include)
        if hits:
            return hits
    return []


def search_domain(query: str, domain: str, count: int = 10) -> list[SearchHit]:
    """Search only the requested source without the legacy fallback to other sites."""
    fn = _tavily if provider() == "tavily" else _bocha
    return fn(query, count, 30, domain)


_BLOCK_MARKERS = re.compile(r"登录|验证码|安全验证|security-check|captcha|访问异常|请稍后", re.I)
_last_fetch = [0.0]


def fetch_page_text(url: str, max_chars: int = 4000) -> str | None:
    """Return visible text, or None when blocked / failed. Rate limited to 1 req/s."""
    wait = 1.0 - (time.time() - _last_fetch[0])
    if wait > 0:
        time.sleep(wait)
    _last_fetch[0] = time.time()
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CareerCraft-student-project"})
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", r.text)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 200 or (_BLOCK_MARKERS.search(text[:500]) and "职位描述" not in text):
        return None
    return text[:max_chars]


if __name__ == "__main__":     # 自检：验证 Key 是否可用
    import sys
    from pathlib import Path

    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    except ImportError:
        pass
    q = " ".join(sys.argv[1:]) or "后端开发实习 深圳 招聘"
    print(f"provider={provider()}  query={q}")
    try:
        results = web_search(q, count=10)
    except SearchError as exc:
        print("失败：", exc)
        sys.exit(1)
    print(f"共 {len(results)} 条")
    for h in results:
        print(f"- [{h.date_text[:10] or '日期未知'}] {h.title}\n  {h.url}")
