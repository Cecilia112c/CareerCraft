"""Scripted provider for tests and offline demos: replays queued responses, records every call."""

from __future__ import annotations

import json
from typing import Callable, Union

from agents.harness.llm.base import LLMResponse, ToolCall

Scripted = Union[str, dict, LLMResponse, Callable[[list[dict]], Union[str, LLMResponse]]]


def tool_call(name: str, arguments: dict | None = None, call_id: str = "call_1") -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=call_id, name=name,
                                            arguments=json.dumps(arguments or {}, ensure_ascii=False))])


class ScriptedProvider:
    def __init__(self, responses: list[Scripted] | None = None):
        self.queue: list[Scripted] = list(responses or [])
        self.calls: list[dict] = []

    def push(self, *responses: Scripted) -> None:
        self.queue.extend(responses)

    def complete(self, messages: list[dict], *, tier: str = "fast", tools: list[dict] | None = None,
                 tool_choice: str = "auto", json_mode: bool = False, temperature: float = 0.3) -> LLMResponse:
        self.calls.append({"messages": [dict(m) for m in messages], "tier": tier, "tool_choice": tool_choice,
                           "tools": [t["function"]["name"] for t in (tools or [])], "json_mode": json_mode})
        if not self.queue:
            raise AssertionError("ScriptedProvider: no more scripted responses")
        item = self.queue.pop(0)
        if callable(item):
            item = item(messages)
        if isinstance(item, LLMResponse):
            return item
        if isinstance(item, dict):
            item = json.dumps(item, ensure_ascii=False)
        return LLMResponse(content=str(item), model="scripted")
