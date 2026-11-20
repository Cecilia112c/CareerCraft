"""Long-term memory: confirmed user preferences (写作风格、求职偏好、沟通方式……).

Write rules (enforced here, not in prompts):
  - explicit user instruction ("以后都…", "记住…") → active immediately
  - anything inferred by a model (tool call) → proposed, the user confirms in the UI
  - same (namespace, key) → the old active value becomes superseded (never overwritten in place)
  - forget → status forgotten, excluded from every projection
"""

from __future__ import annotations

import hashlib
import re

from agents.harness.memory.models import MemoryItem
from agents.harness.memory.store import SQLiteMemoryStore
from agents.harness.spec import NAMESPACES

MAX_VALUE = 200
MAX_ACTIVE_PER_USER = 60


def normalize_value(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())[:MAX_VALUE]


def auto_key(value: str) -> str:
    return "pref_" + hashlib.sha1(normalize_value(value).encode("utf-8")).hexdigest()[:10]


def normalize_key(key: str, value: str) -> str:
    key = re.sub(r"[^\w.\-]", "_", (key or "").strip().lower())[:60].strip("_")
    return key or auto_key(value)


class PreferenceMemory:
    def __init__(self, store: SQLiteMemoryStore):
        self.store = store

    def _check_ns(self, namespace: str) -> None:
        if namespace not in NAMESPACES:
            raise ValueError(f"unknown namespace: {namespace}")

    def propose(self, user_id: str, namespace: str, value: str, *, key: str = "", explicit: bool = False,
                source: str = "tool", evidence: str = "", confidence: float = 0.7) -> MemoryItem | None:
        self._check_ns(namespace)
        value = normalize_value(value)
        if len(value) < 2:
            return None
        key = normalize_key(key, value)
        for item in self.store.list_items(user_id, [namespace], ("active", "proposed")):
            if normalize_value(item.value) == value:          # 同样的内容不重复记
                if explicit and item.status == "proposed":
                    return self.confirm(user_id, item.id)
                return item
        item = self.store.add_item(user_id, namespace, key, value, "proposed", source, evidence[:300], confidence)
        return self.confirm(user_id, item.id, source=source) if explicit else item

    def confirm(self, user_id: str, item_id: int, source: str | None = None) -> MemoryItem | None:
        item = self.store.get_item(item_id)
        if item is None or item.user_id != user_id or item.status not in ("proposed", "active"):
            return None
        for old in self.store.list_items(user_id, [item.namespace], ("active",), key=item.key):
            if old.id != item.id:
                self.store.update_item(old.id, status="superseded")
        active = [a for a in self.store.list_items(user_id, None, ("active",), limit=MAX_ACTIVE_PER_USER + 10)
                  if a.id != item.id]
        for extra in active[MAX_ACTIVE_PER_USER - 1:]:           # 超过上限时淘汰最旧的
            self.store.update_item(extra.id, status="superseded")
        extra = {"source": source} if source else {}
        return self.store.update_item(item.id, status="active", confidence=1.0, **extra)

    def forget(self, user_id: str, item_id: int) -> bool:
        item = self.store.get_item(item_id)
        if item is None or item.user_id != user_id:
            return False
        self.store.update_item(item_id, status="forgotten")
        return True

    def edit(self, user_id: str, item_id: int, value: str) -> MemoryItem | None:
        item = self.store.get_item(item_id)
        if item is None or item.user_id != user_id or item.status == "forgotten":
            return None
        return self.store.update_item(item_id, value=normalize_value(value))

    def active(self, user_id: str, namespaces: tuple[str, ...] | list[str], limit: int = 12) -> list[MemoryItem]:
        return self.store.list_items(user_id, list(namespaces), ("active",), limit=limit)

    def list(self, user_id: str, statuses=("active", "proposed")) -> list[MemoryItem]:
        return self.store.list_items(user_id, None, statuses)
