"""Provider-neutral LLM interface (OpenAI-style messages + function calling)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str          # 原始 JSON 字符串，由工具执行器解析与校验


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    usage: dict = field(default_factory=dict)   # prompt_tokens / completion_tokens


class LLMProvider(Protocol):
    def complete(self, messages: list[dict], *, tier: str = "fast", tools: list[dict] | None = None,
                 tool_choice: str = "auto", json_mode: bool = False, temperature: float = 0.3) -> LLMResponse: ...
