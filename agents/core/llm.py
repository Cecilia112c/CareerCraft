"""Compatibility shim: plain chat completion through the harness provider."""

from __future__ import annotations

from agents.harness.errors import ProviderError as LLMError
from agents.harness.llm.openai_provider import model_for

__all__ = ["LLMError", "chat", "model_for"]


def chat(messages: list[dict], tier: str = "fast", json_mode: bool = True, temperature: float = 0.3) -> str:
    from agents.harness import get_runtime
    return get_runtime().provider.complete(messages, tier=tier, json_mode=json_mode,
                                           temperature=temperature).content
