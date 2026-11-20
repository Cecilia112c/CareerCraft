"""把岗位薪资文本统一换算成「月薪区间（单位 K）」，用于和求职偏好比较。纯代码，不调用大模型。

支持：15-25K·14薪 / 15K-25K / 1.5-2万 / 8000-12000元/月 / 200-300元/天 / 50元/时 / 30-40万/年 / 20K
无法识别（面议、空）返回 None。
"""

from __future__ import annotations

import re

WORK_DAYS_PER_MONTH = 21.75
_NUM = r"(\d+(?:\.\d+)?)"
_UNIT = r"([kK千万wW]|元)?"
_RANGE = re.compile(_NUM + r"\s*" + _UNIT + r"\s*[-~～—–至到]\s*" + _NUM + r"\s*" + _UNIT)
_SINGLE = re.compile(_NUM + r"\s*([kK千万wW]|元)")


def _multiplier(unit: str, value: float) -> float:
    if unit in ("k", "K", "千"):
        return 1.0
    if unit in ("万", "w", "W"):
        return 10.0
    if unit == "元":
        return 0.001
    return 0.001 if value >= 1000 else 1.0     # 没写单位：大数按元，小数按 K


def parse_salary(text: str | None) -> tuple[float, float] | None:
    t = str(text or "").strip()
    if not t or re.search(r"面议|negotiable", t, re.I):
        return None
    m = _RANGE.search(t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(3))
        unit = m.group(4) or m.group(2) or ""
    else:
        m = _SINGLE.search(t)
        if not m:
            return None
        lo = hi = float(m.group(1))
        unit = m.group(2) or ""
    daily = bool(re.search(r"/\s*(天|日)|每天|日薪", t))
    hourly = bool(re.search(r"/\s*(小?时)|时薪", t))
    yearly = bool(re.search(r"/\s*年|年薪", t))
    mult = 0.001 if (daily or hourly) and not unit else _multiplier(unit, hi)   # 日薪/时薪没写单位时按元
    lo, hi = lo * mult, hi * mult
    if daily:
        lo, hi = lo * WORK_DAYS_PER_MONTH, hi * WORK_DAYS_PER_MONTH
    elif hourly:
        lo, hi = lo * 8 * WORK_DAYS_PER_MONTH, hi * 8 * WORK_DAYS_PER_MONTH
    elif yearly:
        lo, hi = lo / 12, hi / 12
    if lo > hi:
        lo, hi = hi, lo
    if hi <= 0 or hi > 1000:       # 明显不是薪资
        return None
    return round(lo, 1), round(hi, 1)


def format_k(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return ""
    return f"{low:g}K" if low == high else f"{low:g}-{high:g}K"
