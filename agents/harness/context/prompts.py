"""Prompt templates: {{var}} filling (single pass) and untrusted-data wrapping."""

from __future__ import annotations

import json
import re
from pathlib import Path

KERNEL_PATH = Path(__file__).resolve().parents[1] / "prompts" / "kernel.md"


def _to_text(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=1, default=str)


def fill(template: str, variables: dict | None = None, name: str = "prompt") -> str:
    variables = variables or {}
    missing = [k for k in re.findall(r"\{\{(\w+)\}\}", template) if k not in variables]
    if missing:
        raise KeyError(f"{name} missing variables: {missing}")
    return re.sub(r"\{\{(\w+)\}\}", lambda m: _to_text(variables[m.group(1)]), template)


def load_prompt(path: Path, variables: dict | None = None) -> str:
    return fill(path.read_text(encoding="utf-8"), variables, path.name)


def kernel_prompt() -> str:
    return KERNEL_PATH.read_text(encoding="utf-8")


def data_block(tag: str, content) -> str:
    """Wrap untrusted material so the model treats it as data, never as instructions."""
    text = _to_text(content).replace(f"</data:{tag}>", "")
    return f'<data:{tag} trust="untrusted">\n{text}\n</data:{tag}>'
