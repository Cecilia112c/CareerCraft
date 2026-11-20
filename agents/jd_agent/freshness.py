"""Turn '3天前' / '昨天' / '11月12日' / ISO dates into a date, deterministically."""

from __future__ import annotations

import os
import re
from datetime import date, timedelta


def parse_published(text: str, today: date | None = None) -> date | None:
    if not text:
        return None
    today = today or date.today()
    t = str(text).strip()

    m = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    if re.search(r"刚刚|今天|今日|\d+\s*(分钟|小时)前|just now|hours? ago|minutes? ago", t, re.I):
        return today
    if "昨天" in t or "昨日" in t or re.search(r"yesterday", t, re.I):
        return today - timedelta(days=1)
    if "前天" in t:
        return today - timedelta(days=2)
    m = re.search(r"(\d+)\s*(天|日)前|(\d+)\s*days? ago", t, re.I)
    if m:
        return today - timedelta(days=int(m.group(1) or m.group(3)))
    m = re.search(r"(\d+)\s*(周|星期)前|(\d+)\s*weeks? ago", t, re.I)
    if m:
        return today - timedelta(weeks=int(m.group(1) or m.group(3)))
    m = re.search(r"(\d+)\s*个?月前", t)
    if m:
        return today - timedelta(days=30 * int(m.group(1)))
    m = re.search(r"(\d{1,2})\s*[月/-]\s*(\d{1,2})\s*日?", t)
    if m:
        try:
            d = date(today.year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
        return d if d <= today else date(today.year - 1, d.month, d.day)
    return None


DEFAULT_FRESH_DAYS = 90   # 只保留近 3 个月发布的岗位


def fresh_days() -> int:
    """时效窗口（天），可在 .env 用 JOB_FRESH_DAYS 修改，默认 90 天（近 3 个月）。"""
    try:
        return max(1, int(os.getenv("JOB_FRESH_DAYS", DEFAULT_FRESH_DAYS)))
    except ValueError:
        return DEFAULT_FRESH_DAYS


def is_fresh(published: date | None, days: int | None = None, today: date | None = None) -> bool | None:
    """True/False when known, None when the date is unknown."""
    if published is None:
        return None
    days = days or fresh_days()
    today = today or date.today()
    return 0 <= (today - published).days <= days
