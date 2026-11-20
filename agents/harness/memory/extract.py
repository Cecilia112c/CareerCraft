"""Deterministic detection of explicit, durable preferences in a user instruction.

Only sentences with a durability marker ("以后", "记住", "不要再"…) count. One-off requests
("这句改短一点") stay in working memory and never become long-term preferences.
"""

from __future__ import annotations

import re

MARKERS = re.compile(r"以后|今后|之后都|从现在起|从今以后|一直|总是|始终|每次都|记住|不要再|别再|永远|默认都")
_SPLIT = re.compile(r"[。！!？?\n；;]+")


def explicit_preferences(instruction: str, limit: int = 3) -> list[str]:
    out: list[str] = []
    for sentence in _SPLIT.split(instruction or ""):
        s = sentence.strip(" ，,")
        if 4 <= len(s) <= 120 and MARKERS.search(s):
            s = re.sub(r"^(请|麻烦)?(帮我)?(记住|记一下)[:：，,]?", "", s).strip(" ，,")
            if len(s) >= 4 and s not in out:
                out.append(s)
    return out[:limit]


def wants_memory(instruction: str) -> bool:
    return bool(explicit_preferences(instruction))
