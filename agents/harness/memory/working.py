"""Working memory: per (user, agent, session) recent turns + a rolling summary.

When a session grows beyond MAX_TURNS, the older turns are folded into the summary
(LLM summarizer if provided, extractive fallback otherwise) and deleted.
"""

from __future__ import annotations

import logging
from typing import Callable

from agents.harness.memory.models import WorkingTurn, WorkingView
from agents.harness.memory.store import SQLiteMemoryStore

log = logging.getLogger("careercraft.harness.memory")

MAX_TURNS = 12          # 超过就压缩
KEEP_RECENT = 6         # 压缩后保留的最近轮数
MAX_TURN_CHARS = 1200
MAX_SUMMARY_CHARS = 1200

SummarizerFn = Callable[[str, list[WorkingTurn]], str]


def extractive_summary(previous: str, turns: list[WorkingTurn]) -> str:
    """No-LLM fallback: keep the user's requests (they carry intent), newest last."""
    asks = [t.content[:120] for t in turns if t.role == "user"]
    text = (previous + "；" if previous else "") + "；".join(asks)
    return text[-MAX_SUMMARY_CHARS:]


class WorkingMemory:
    def __init__(self, store: SQLiteMemoryStore, summarizer: SummarizerFn | None = None):
        self.store = store
        self.summarizer = summarizer

    def append(self, user_id: str, agent: str, session: str, role: str, content: str) -> None:
        if not session or not content.strip():
            return
        self.store.add_turn(user_id, agent, session, role, content.strip()[:MAX_TURN_CHARS])
        self.compact(user_id, agent, session)

    def view(self, user_id: str, agent: str, session: str, keep_recent: int = KEEP_RECENT) -> WorkingView:
        if not session:
            return WorkingView()
        turns = self.store.list_turns(user_id, agent, session)
        return WorkingView(summary=self.store.get_summary(user_id, agent, session), turns=turns[-keep_recent:])

    def compact(self, user_id: str, agent: str, session: str) -> None:
        turns = self.store.list_turns(user_id, agent, session)
        if len(turns) <= MAX_TURNS:
            return
        old, previous = turns[:-KEEP_RECENT], self.store.get_summary(user_id, agent, session)
        summary = ""
        if self.summarizer:
            try:
                summary = (self.summarizer(previous, old) or "").strip()
            except Exception as exc:  # noqa: BLE001  摘要失败不能影响主流程
                log.warning("working memory summarizer failed: %s", exc)
        summary = (summary or extractive_summary(previous, old))[:MAX_SUMMARY_CHARS]
        self.store.set_summary(user_id, agent, session, summary)
        self.store.delete_turns([t.id for t in old])

    def clear(self, user_id: str, agent: str, session: str) -> None:
        self.store.clear_session(user_id, agent, session)
