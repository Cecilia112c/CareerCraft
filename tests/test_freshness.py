from datetime import date

from agents.jd_agent.freshness import is_fresh, parse_published

TODAY = date(2026, 11, 15)


def test_relative_dates():
    assert parse_published("今天", TODAY) == TODAY
    assert parse_published("5小时前", TODAY) == TODAY
    assert parse_published("昨天", TODAY) == date(2026, 11, 14)
    assert parse_published("3天前", TODAY) == date(2026, 11, 12)
    assert parse_published("2周前", TODAY) == date(2026, 11, 1)


def test_absolute_dates():
    assert parse_published("2026-11-10T08:00:00+08:00", TODAY) == date(2026, 11, 10)
    assert parse_published("发布于11月12日", TODAY) == date(2026, 11, 12)
    assert parse_published("12月30日", TODAY) == date(2025, 12, 30)   # 未来日期视为去年


def test_unknown():
    assert parse_published("", TODAY) is None
    assert parse_published("用户导入", TODAY) is None


def test_is_fresh():
    assert is_fresh(date(2026, 11, 9), 7, TODAY) is True
    assert is_fresh(date(2026, 11, 7), 7, TODAY) is False
    assert is_fresh(None, 7, TODAY) is None
