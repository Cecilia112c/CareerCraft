"""Deterministic fact check: rewritten text must not introduce new numbers or tech terms."""

from __future__ import annotations

import re

NUMBER = re.compile(r"\d+(?:\.\d+)?")
TERM = re.compile(r"[A-Za-z][A-Za-z0-9+#]*(?:[.\-/][A-Za-z0-9+#]+)*")
# 通用词，不视为“新增技术事实”
GENERIC = {
    "ai", "api", "apis", "app", "ui", "ux", "web", "it", "sop", "prd", "star", "jd", "pc", "h5",
    "ok", "vs", "etc", "and", "or", "the", "of", "to", "in", "for", "on", "with", "a", "an",
}


def _numbers(text: str) -> set[str]:
    out = set()
    for n in NUMBER.findall(text):
        out.add(n)
        if "." in n:
            out.add(n.rstrip("0").rstrip("."))
    return out


def _terms(text: str) -> set[str]:
    return {t.lower() for t in TERM.findall(text) if len(t) >= 2 or t.isupper()}


def check_text(new_text: str, reference: str) -> list[str]:
    """Return a list of problems; empty means OK."""
    problems: list[str] = []
    if not new_text.strip():
        return ["内容为空"]
    ref_numbers = _numbers(reference)
    new_numbers = [n for n in NUMBER.findall(new_text)
                   if n not in ref_numbers and n.rstrip("0").rstrip(".") not in ref_numbers]
    if new_numbers:
        problems.append("新增了原文没有的数字：" + "、".join(dict.fromkeys(new_numbers)))
    ref_lower = reference.lower()
    new_terms = [t for t in _terms(new_text) if t not in GENERIC and t not in ref_lower]
    if new_terms:
        problems.append("新增了原文没有的技术词：" + "、".join(sorted(new_terms)))
    return problems
