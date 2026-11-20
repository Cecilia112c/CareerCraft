"""ContextBuilder: a pure compiler from ordered slots to chat messages + a manifest.

It never reads the database, memory or tools; the runtime resolves those first and hands
over plain text slots. Order is fixed by the caller:

  system:  kernel → agent prompt → skills → tool protocol → output schema → long-term preferences → working memory
  user:    materials (<data:...>) → current instruction (always last, never truncated)

When the estimate exceeds the budget, optional slots are truncated/dropped from the lowest
priority upwards. Required slots are never touched; if they alone exceed the budget the model
is not called (ContextBudgetExceeded).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

from agents.harness.context.budget import estimate_tokens, truncate_to_tokens
from agents.harness.errors import ContextBudgetExceeded

Trust = Literal["authoritative", "developer", "user_confirmed", "user_asserted", "derived", "external_untrusted"]


@dataclass
class Slot:
    name: str
    content: str
    role: Literal["system", "user"] = "system"
    trust: Trust = "developer"
    priority: int = 50          # 预算不足时从低到高裁剪
    required: bool = False
    max_tokens: int | None = None


@dataclass
class ContextManifest:
    entries: list[dict] = field(default_factory=list)
    total_tokens: int = 0
    budget: int = 0
    context_hash: str = ""

    def as_dict(self) -> dict:
        return {"entries": self.entries, "total_tokens": self.total_tokens, "budget": self.budget,
                "context_hash": self.context_hash}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class ContextBuilder:
    def build(self, slots: list[Slot], max_input_tokens: int) -> tuple[list[dict], ContextManifest]:
        work = []
        for s in slots:
            if not s.content or not s.content.strip():
                continue
            content, truncated = s.content, False
            if s.max_tokens and not s.required and estimate_tokens(content) > s.max_tokens:
                content, truncated = truncate_to_tokens(content, s.max_tokens), True
            work.append({"slot": s, "content": content, "truncated": truncated, "dropped": False})

        required_tokens = sum(estimate_tokens(w["content"]) for w in work if w["slot"].required)
        if required_tokens > max_input_tokens:
            raise ContextBudgetExceeded(f"必需上下文约 {required_tokens} tokens，超过预算 {max_input_tokens}")

        def total() -> int:
            return sum(estimate_tokens(w["content"]) for w in work if not w["dropped"])

        over = total() - max_input_tokens
        for w in sorted((w for w in work if not w["slot"].required), key=lambda w: w["slot"].priority):
            if over <= 0:
                break
            size = estimate_tokens(w["content"])
            keep = size - over
            if keep < 40:
                w["dropped"], over = True, over - size
            else:
                w["content"], w["truncated"] = truncate_to_tokens(w["content"], keep), True
                over -= size - estimate_tokens(w["content"])

        system_parts = [w["content"] for w in work if not w["dropped"] and w["slot"].role == "system"]
        user_parts = [w["content"] for w in work if not w["dropped"] and w["slot"].role == "user"]
        messages = [{"role": "system", "content": "\n\n".join(system_parts)},
                    {"role": "user", "content": "\n\n".join(user_parts) or "请按要求只输出 JSON。"}]
        manifest = ContextManifest(
            entries=[{"name": w["slot"].name, "trust": w["slot"].trust, "tokens": estimate_tokens(w["content"]),
                      "sha": _sha(w["content"]), "truncated": w["truncated"], "dropped": w["dropped"]}
                     for w in work],
            total_tokens=total(), budget=max_input_tokens,
            context_hash=_sha(messages[0]["content"] + "\x00" + messages[1]["content"]),
        )
        return messages, manifest
