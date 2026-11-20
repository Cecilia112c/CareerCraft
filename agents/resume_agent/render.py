"""Render ResumeDoc into the ASU-style HTML template."""

from __future__ import annotations

import json
from pathlib import Path

from agents.core.schemas import ResumeDoc

TEMPLATE = Path(__file__).parent / "template" / "resume_template.html"


def render_html(doc: ResumeDoc, interactive: bool = False) -> str:
    payload = json.dumps(doc.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    # 把所有 "<" 转义成合法的 JSON 转义序列，防止简历内容中的 "</script>" / "<!--" 破坏脚本块
    payload = payload.replace("<", "\\u003c")
    html = TEMPLATE.read_text(encoding="utf-8")
    return html.replace("__INTERACTIVE__", "true" if interactive else "false").replace(
        "__RESUME_JSON__", payload)
