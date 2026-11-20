"""OpenAI-compatible provider (DeepSeek / 通义千问 / Kimi / OpenAI), with function calling."""

from __future__ import annotations

import os
import threading

from agents.harness.errors import ProviderError
from agents.harness.llm.base import LLMResponse, ToolCall


def model_for(tier: str) -> str:
    if tier == "strong":
        return os.getenv("LLM_MODEL_STRONG") or os.getenv("LLM_MODEL_FAST") or "deepseek-chat"
    return os.getenv("LLM_MODEL_FAST") or os.getenv("LLM_MODEL_STRONG") or "deepseek-chat"


class OpenAIProvider:
    def __init__(self) -> None:
        self._client = None
        self._lock = threading.Lock()

    def _get_client(self):
        with self._lock:
            if self._client is None:
                key = os.getenv("LLM_API_KEY", "").strip()
                if not key:
                    raise ProviderError("未配置 LLM_API_KEY，请在 CareerCraft/.env 中填写")
                from openai import OpenAI
                self._client = OpenAI(api_key=key, base_url=os.getenv("LLM_BASE_URL") or None,
                                      timeout=float(os.getenv("LLM_TIMEOUT", "90")), max_retries=2)
            return self._client

    def complete(self, messages: list[dict], *, tier: str = "fast", tools: list[dict] | None = None,
                 tool_choice: str = "auto", json_mode: bool = False, temperature: float = 0.3) -> LLMResponse:
        kwargs: dict = {"model": model_for(tier), "messages": messages, "temperature": temperature}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        elif json_mode and os.getenv("LLM_JSON_MODE", "1") == "1":
            kwargs["response_format"] = {"type": "json_object"}   # 带工具时不能同时强制 JSON
        try:
            resp = self._get_client().chat.completions.create(**kwargs)
        except ProviderError:
            raise
        except Exception as exc:  # network / auth / quota / bad request
            raise ProviderError(f"大模型调用失败：{exc}") from exc
        msg = resp.choices[0].message
        calls = [ToolCall(id=c.id, name=c.function.name, arguments=c.function.arguments or "{}")
                 for c in (getattr(msg, "tool_calls", None) or [])]
        usage = {}
        if getattr(resp, "usage", None):
            usage = {"prompt_tokens": resp.usage.prompt_tokens, "completion_tokens": resp.usage.completion_tokens}
        return LLMResponse(content=msg.content or "", tool_calls=calls, model=kwargs["model"], usage=usage)
