"""Per-call inputs and outputs of AgentRuntime.invoke()."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel

from agents.harness.spec import AgentSpec

Report = Callable[[int, str], None]


def noop_report(progress: int, stage: str) -> None:  # noqa: ARG001
    return None


@dataclass(frozen=True)
class ExecutionContext:
    """Who is calling and what they are allowed to do. Built by the backend, never by the agent.

    scopes        权限范围，例如 {"material:read", "memory:read", "memory:write"}；工具需要的范围必须全部具备
    allow_writes  用户本轮明确授权写入（例如说了“记住……”），写类工具可直接生效，否则只生成待确认提议
    tool_allowlist 任务级白名单，再与 AgentSpec.tools 求交集；None 表示不额外收窄
    session       工作记忆的会话键，例如 "resume:12" / "interview:3"
    """
    user_id: str = "anonymous"
    session: str = ""
    workflow_step_id: str = ""
    scopes: frozenset[str] = frozenset()
    allow_writes: bool = False
    tool_allowlist: frozenset[str] | None = None
    report: Report = noop_report

    @staticmethod
    def for_user(user_id: Any, *, session: str = "", scopes=(), allow_writes: bool = False,
                 tool_allowlist=None, report: Report = noop_report, workflow_step_id: str = "") -> "ExecutionContext":
        return ExecutionContext(
            user_id=str(user_id), session=session, workflow_step_id=workflow_step_id,
            scopes=frozenset(scopes), allow_writes=allow_writes,
            tool_allowlist=frozenset(tool_allowlist) if tool_allowlist is not None else None, report=report,
        )


ANONYMOUS = ExecutionContext()


@dataclass
class InvocationRequest:
    spec: AgentSpec
    variables: dict[str, Any] = field(default_factory=dict)    # 填入系统提示模板
    materials: dict[str, Any] = field(default_factory=dict)    # 不可信资料，按名称放进 <data:name>
    instruction: str = ""                                      # 用户本轮的完整指令，始终放在最后
    ctx: ExecutionContext = ANONYMOUS


@dataclass
class InvocationResult:
    output: BaseModel
    run: dict
    memory_events: list[dict] = field(default_factory=list)   # 本轮新增/更新的记忆（给前端提示“已记住……”）
