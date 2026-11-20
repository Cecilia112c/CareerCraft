"""Memory facade used by the runtime and the backend. Callers never touch the store tables."""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.harness.memory.extract import explicit_preferences
from agents.harness.memory.longterm import PreferenceMemory
from agents.harness.memory.models import MemoryItem, WorkingView
from agents.harness.memory.store import SQLiteMemoryStore
from agents.harness.memory.working import SummarizerFn, WorkingMemory
from agents.harness.spec import MemoryPolicy


@dataclass
class MemoryContext:
    preferences: list[MemoryItem] = field(default_factory=list)
    working: WorkingView = field(default_factory=WorkingView)

    def render_preferences(self) -> str:
        if not self.preferences:
            return ""
        lines = [f"- {p.value}" for p in self.preferences]
        return "【用户长期偏好】（用户确认过，在不违反事实约束的前提下遵循）\n" + "\n".join(lines)

    def render_working(self) -> str:
        text = self.working.render()
        return "【本会话的工作记忆】（近期指令与结果，用于保持前后一致）\n" + text if text else ""


class MemoryManager:
    def __init__(self, store: SQLiteMemoryStore, summarizer: SummarizerFn | None = None):
        self.store = store
        self.preferences = PreferenceMemory(store)
        self.working = WorkingMemory(store, summarizer)

    def prepare(self, user_id: str, agent: str, session: str, policy: MemoryPolicy) -> MemoryContext:
        prefs = self.preferences.active(user_id, policy.read_namespaces, policy.max_preferences) \
            if policy.read_namespaces else []
        working = self.working.view(user_id, agent, session) if policy.use_working else WorkingView()
        return MemoryContext(preferences=prefs, working=working)

    def capture_explicit(self, user_id: str, policy: MemoryPolicy, instruction: str) -> list[MemoryItem]:
        """User said "以后/记住/不要再…" → store as active preference in the spec's default namespace."""
        if not policy.write_namespaces:
            return []
        out = []
        for text in explicit_preferences(instruction):
            item = self.preferences.propose(user_id, policy.write_namespaces[0], text, explicit=True,
                                            source="explicit_instruction", evidence=instruction)
            if item:
                out.append(item)
        return out

    def record_turn(self, user_id: str, agent: str, session: str, instruction: str, result_summary: str) -> None:
        if instruction.strip():
            self.working.append(user_id, agent, session, "user", instruction)
        if result_summary.strip():
            self.working.append(user_id, agent, session, "assistant", result_summary)

    def record_episode(self, user_id: str, agent: str, spec_id: str, session: str, summary: str,
                       status: str) -> None:
        self.store.add_episode(user_id, agent, spec_id, session, summary[:300], status)
