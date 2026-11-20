"""Tool contract. Every tool declares its argument schema, required scopes and side effect."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Mapping

from pydantic import BaseModel

if TYPE_CHECKING:
    from agents.harness.memory.manager import MemoryManager
    from agents.harness.spec import AgentSpec

SideEffect = Literal["none", "read", "write", "network"]


@dataclass(frozen=True)
class ToolContext:
    """What a tool may know about the call. The owner comes from here, never from tool arguments."""
    user_id: str
    spec: "AgentSpec"
    session: str
    scopes: frozenset[str]
    allow_writes: bool
    materials: Mapping[str, Any] = field(default_factory=dict)
    memory: "MemoryManager | None" = None


class ToolResult(BaseModel):
    ok: bool
    data: Any = None
    error_code: str | None = None
    message: str = ""
    events: list[dict] = []          # 例如记忆写入事件，供运行时汇总给前端


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[BaseModel]]      # 必须 extra="forbid"
    scopes: ClassVar[frozenset[str]] = frozenset()
    side_effect: ClassVar[SideEffect] = "read"
    max_calls: ClassVar[int] = 3               # 单次调用内最多调用几次
    timeout_s: ClassVar[float] = 15.0

    def schema(self) -> dict:
        params = self.args_model.model_json_schema()
        params.pop("title", None)
        return {"type": "function",
                "function": {"name": self.name, "description": self.description, "parameters": params}}

    @abstractmethod
    def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult: ...
