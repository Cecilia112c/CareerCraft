"""Tool authorization. Default deny; a call must pass every layer:

  1. 白名单：AgentSpec.tools ∩ ExecutionContext.tool_allowlist ∩ 已注册工具（不可见的工具不会发给模型）
  2. 权限范围：tool.scopes ⊆ ctx.scopes（由后端按用户/任务授予，例如面试 agent 没有 memory:write）
  3. 频率：单个工具 ≤ tool.max_calls，总数 ≤ spec.budget.max_tool_calls
  4. 归属：参数里不允许出现 user_id 之类字段，归属一律取自 ctx（注册时也会检查）
  5. 写入：side_effect=write 时，只有 ctx.allow_writes 才直接生效，否则工具只能生成“待确认”提议
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.harness.request import ExecutionContext
from agents.harness.spec import AgentSpec
from agents.harness.tools.base import Tool
from agents.harness.tools.registry import FORBIDDEN_ARGS, ToolRegistry


@dataclass
class Decision:
    allowed: bool
    code: str = "ok"
    message: str = ""
    needs_confirmation: bool = False


class ToolPolicy:
    def visible(self, spec: AgentSpec, ctx: ExecutionContext, registry: ToolRegistry) -> dict[str, Tool]:
        names = set(spec.tools)
        if ctx.tool_allowlist is not None:
            names &= set(ctx.tool_allowlist)
        out = {}
        for name in sorted(names):
            tool = registry.get(name)
            if tool is not None and tool.scopes <= ctx.scopes:
                out[name] = tool
        return out

    def authorize(self, name: str, raw_args: dict, visible: dict[str, Tool], ctx: ExecutionContext,
                  spec: AgentSpec, counts: dict[str, int]) -> Decision:
        tool = visible.get(name)
        if tool is None:
            return Decision(False, "tool_not_allowed", f"工具 {name} 不在本次任务的白名单内")
        missing = tool.scopes - ctx.scopes
        if missing:
            return Decision(False, "missing_scope", f"缺少权限：{sorted(missing)}")
        if counts.get(name, 0) >= tool.max_calls:
            return Decision(False, "rate_limited", f"{name} 调用次数已达上限 {tool.max_calls}")
        if sum(counts.values()) >= spec.budget.max_tool_calls:
            return Decision(False, "rate_limited", "本次任务的工具调用总数已达上限")
        if FORBIDDEN_ARGS & set(raw_args):
            return Decision(False, "owner_override_forbidden", "不允许在参数中指定用户")
        return Decision(True, needs_confirmation=tool.side_effect == "write" and not ctx.allow_writes)
