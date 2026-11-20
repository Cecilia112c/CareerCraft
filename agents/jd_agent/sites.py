"""Search source rules for market samples and user-selected job cards."""

from urllib.parse import urlsplit, urlunsplit

SITES = {
    "boss": ("zhipin.com", ("/job_detail/",)),
    "tencent": ("join.qq.com", ("/post_detail", "/job/")),
    "bytedance": ("jobs.bytedance.com", ("/position/",)),
    "alibaba": ("talent.alibaba.com", ("/job/", "/position/")),
    "huawei": ("career.huawei.com", ("/recruitment/", "/job/")),
    "nowcoder": ("nowcoder.com", ("/jobs/detail/",)),
    "shixiseng": ("shixiseng.com", ("/intern/",)),
}
DEFAULT_SOURCES = list(SITES)
BOSS_CITY_CODES = {"深圳": "101280600", "北京": "101010100", "上海": "101020100",
                   "广州": "101280100", "杭州": "101210100"}


def site_for_url(raw: str, sources: list[str] | None = None) -> tuple[str, str] | None:
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower()
    for site in DEFAULT_SOURCES if sources is None else sources:
        if site not in SITES:
            continue
        domain, paths = SITES[site]
        if (host == domain or host.endswith("." + domain)) and any(p in parts.path for p in paths):
            return site, urlunsplit(("https", host, parts.path.rstrip("/"), "", ""))
    return None
