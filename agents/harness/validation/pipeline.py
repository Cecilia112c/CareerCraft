"""Output validation: syntax → schema → domain validators. Produces a repair message when invalid."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from agents.harness.request import InvocationRequest


def extract_json(raw: str) -> str:
    raw = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if fenced:
        raw = fenced.group(1).strip()
    if raw.startswith("{") or raw.startswith("["):
        return raw
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        return raw[start:end + 1]
    return raw


@dataclass
class ValidationReport:
    ok: bool
    output: BaseModel | None = None
    stage: str = ""                       # syntax / schema / domain
    issues: list[str] = field(default_factory=list)

    def repair_message(self) -> str:
        bullet = "\n".join(f"- {i}" for i in self.issues[:6])
        stage = {"syntax": "格式", "schema": "结构", "domain": "内容"}.get(self.stage, "")
        return f"上一次输出没有通过{stage}校验：\n{bullet}\n请修正后只输出完整的 JSON。"


def validate_output(raw: str, request: "InvocationRequest") -> ValidationReport:
    spec = request.spec
    text = extract_json(raw)
    if not text.startswith(("{", "[")):
        return ValidationReport(False, stage="syntax", issues=["没有找到 JSON 对象"])
    try:
        output = spec.output.model_validate_json(text)
    except ValidationError as exc:
        stage = "syntax" if any(e.get("type") == "json_invalid" for e in exc.errors()) else "schema"
        issues = [f"{'.'.join(map(str, e.get('loc', ())))}: {e.get('msg')}" for e in exc.errors()[:6]]
        return ValidationReport(False, stage=stage, issues=issues)
    issues: list[str] = []
    for validator in spec.validators:
        issues += [str(i) for i in (validator(output, request) or [])]
    if issues:
        return ValidationReport(False, output=output, stage="domain", issues=issues)
    return ValidationReport(True, output=output)
