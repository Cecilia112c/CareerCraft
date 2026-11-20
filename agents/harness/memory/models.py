"""Memory records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# 长期记忆状态：proposed（待用户确认）→ active（生效）→ superseded（被同 key 新值替代）/ forgotten（用户删除）
STATUSES = ("proposed", "active", "superseded", "forgotten")


@dataclass
class MemoryItem:
    id: int
    user_id: str
    namespace: str
    key: str
    value: str
    status: str
    source: str = ""          # explicit_instruction / tool / user_manual / confirmed_proposal
    evidence: str = ""        # 触发这条记忆的原话（截断）
    confidence: float = 1.0
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class WorkingTurn:
    id: int
    role: str                 # user / assistant
    content: str
    created_at: str = ""


@dataclass
class WorkingView:
    summary: str = ""
    turns: list[WorkingTurn] = field(default_factory=list)

    def render(self) -> str:
        parts = []
        if self.summary:
            parts.append("此前对话摘要：" + self.summary)
        for t in self.turns:
            parts.append(f"[{'用户' if t.role == 'user' else '助手'}] {t.content}")
        return "\n".join(parts)


@dataclass
class Episode:
    id: int
    user_id: str
    agent: str
    spec_id: str
    session: str
    summary: str
    status: str
    created_at: str = ""
