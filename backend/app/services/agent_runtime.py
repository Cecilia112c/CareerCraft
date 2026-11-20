"""The ONLY place where the backend grants agent permissions.

Agents never grant themselves scopes: the backend builds an ExecutionContext per call.
  resume     读资料（get_material）、读/写长期偏好
  parser/jd  无工具权限（纯抽取）
  interview  无任何权限：没有工具、只能用 interview 命名空间的记忆（由 spec 限定）
"""

from __future__ import annotations

from agents.harness import ExecutionContext, configure, get_runtime, noop_report
from agents.harness.memory import wants_memory
from backend.app.config import DATA_DIR

AGENT_SCOPES: dict[str, frozenset[str]] = {
    "parser": frozenset(),
    "jd": frozenset(),
    "knowledge": frozenset(),
    "resume": frozenset({"material:read", "memory:read", "memory:write", "kb:read"}),
    "interview": frozenset(),
}


def init_agent_runtime() -> None:
    configure(memory_path=DATA_DIR / "agent_memory.db")
    from backend.app.agent_tools.knowledge_search import SearchKnowledgeTool
    get_runtime().tools.register(SearchKnowledgeTool())


def agent_ctx(user_id: int, agent: str, *, session: str = "", instruction: str = "",
              report=noop_report) -> ExecutionContext:
    from backend.app.workflows.engine import current_step_id
    return ExecutionContext.for_user(
        user_id, session=session, scopes=AGENT_SCOPES.get(agent, frozenset()),
        allow_writes=wants_memory(instruction),     # 用户说了“以后/记住…”才允许写入直接生效
        report=report, workflow_step_id=current_step_id(),
    )


def memory():
    return get_runtime().memory
