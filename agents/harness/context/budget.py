"""Token estimation without a tokenizer dependency (good enough for budgeting)."""

from __future__ import annotations

import re

_CJK = re.compile(r"[㐀-鿿豈-﫿　-〿＀-￯]")


def estimate_tokens(text: str) -> int:
    """CJK chars ≈ 1 token each; other text ≈ 4 chars per token."""
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    return cjk + (len(text) - cjk + 3) // 4


SUFFIX = "\n…（已截断）"


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Result (including the suffix) never exceeds max_tokens."""
    if estimate_tokens(text) <= max_tokens:
        return text
    budget = max(0, max_tokens - estimate_tokens(SUFFIX))
    lo, hi = 0, len(text)
    while lo < hi:                      # binary search on character length
        mid = (lo + hi + 1) // 2
        if estimate_tokens(text[:mid]) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + SUFFIX
