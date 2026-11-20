"""博查接入测试：用假的 httpx.post 验证请求参数、结果解析、错误码与降级逻辑（不联网）。"""

import pytest

from agents.jd_agent import search_api
from agents.jd_agent.search_api import SearchError, web_search


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


def ok(values):
    return FakeResponse(200, {"code": 200, "log_id": "x", "msg": None,
                              "data": {"_type": "SearchResponse", "webPages": {"value": values}}})


HIT = {"name": "「深圳后端开发实习生招聘」- BOSS直聘", "url": "https://www.zhipin.com/job_detail/abc.html",
       "snippet": "岗位职责……", "summary": "负责后端服务开发，要求熟悉 Go", "siteName": "BOSS直聘",
       "datePublished": "2026-11-12T00:00:00+08:00"}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("BOCHA_API_KEY", "sk-test")
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("BOCHA_API_URL", raising=False)
    monkeypatch.delenv("JOB_FRESH_DAYS", raising=False)
    monkeypatch.setattr(search_api.time, "sleep", lambda s: None)


def test_request_and_parse(monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        return ok([HIT])

    monkeypatch.setattr(search_api.httpx, "post", fake_post)
    hits = web_search("后端开发实习 深圳", count=20)
    url, body, headers = calls[0]
    assert url == "https://api.bocha.cn/v1/web-search"
    assert headers["Authorization"] == "Bearer sk-test"
    today = search_api.date.today()
    start = today - search_api.timedelta(days=90)
    assert body == {"query": "后端开发实习 深圳", "freshness": f"{start.isoformat()}..{today.isoformat()}",
                    "summary": True, "count": 20, "include": "zhipin.com"}
    assert hits[0].url.endswith("abc.html")
    assert hits[0].snippet.startswith("负责后端服务开发")      # 优先用 summary
    assert hits[0].date_text.startswith("2026-11-12")


def test_fallback_when_empty(monkeypatch):
    bodies = []

    def fake_post(url, json=None, headers=None, timeout=None):
        bodies.append(json)
        return ok([HIT]) if json["freshness"] == "noLimit" and json["include"] == "zhipin.com" else ok([])

    monkeypatch.setattr(search_api.httpx, "post", fake_post)
    assert len(web_search("后端", count=10)) == 1
    assert [(b["include"].count("|") > 0, b["freshness"] == "noLimit") for b in bodies] == [
        (False, False), (True, False), (False, True)]


def test_freshness_values():
    d = search_api.date(2026, 11, 15)
    assert search_api.bocha_freshness(7, d) == "oneWeek"
    assert search_api.bocha_freshness(90, d) == "2026-08-17..2026-11-15"
    assert search_api.bocha_freshness(None, d) == "noLimit"


@pytest.mark.parametrize("status,word", [(401, "API Key 无效"), (403, "余额不足")])
def test_fatal_errors_not_retried(monkeypatch, status, word):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(url)
        return FakeResponse(status, {"code": status, "msg": "err", "log_id": "L1"})

    monkeypatch.setattr(search_api.httpx, "post", fake_post)
    with pytest.raises(SearchError) as info:
        web_search("后端")
    assert word in str(info.value) and "L1" in str(info.value)
    assert len(calls) == 1


def test_rate_limit_is_retried(monkeypatch):
    responses = iter([FakeResponse(429, {"code": 429}), ok([HIT])])
    monkeypatch.setattr(search_api.httpx, "post", lambda *a, **k: next(responses))
    assert len(web_search("后端")) == 1


def test_missing_key(monkeypatch):
    monkeypatch.delenv("BOCHA_API_KEY")
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    with pytest.raises(SearchError, match="BOCHA_API_KEY"):
        web_search("后端")
