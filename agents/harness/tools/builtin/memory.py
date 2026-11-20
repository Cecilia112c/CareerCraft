"""Memory tools. Namespaces are taken from the spec's MemoryPolicy, never from arguments."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agents.harness.tools.base import Tool, ToolContext, ToolResult


class RecallArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=50, description="可选关键词，为空返回全部生效偏好")


class RecallPreferencesTool(Tool):
    name = "recall_preferences"
    description = "查询用户已确认的长期偏好（写作风格、求职偏好等）。"
    args_model = RecallArgs
    scopes = frozenset({"memory:read"})
    side_effect = "read"
    max_calls = 2

    def run(self, args: RecallArgs, ctx: ToolContext) -> ToolResult:
        if ctx.memory is None or not ctx.spec.memory.read_namespaces:
            return ToolResult(ok=True, data=[])
        items = ctx.memory.preferences.active(ctx.user_id, ctx.spec.memory.read_namespaces, limit=30)
        if args.query:
            items = [i for i in items if args.query in i.value or args.query in i.key]
        return ToolResult(ok=True, data=[{"key": i.key, "value": i.value} for i in items])


class RememberArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=2, max_length=200, description="要记住的偏好，用一句话陈述，例如“简历中英文技术名词保持原文”")
    key: str = Field(default="", max_length=60, description="可选的主题键，同一主题的新偏好会替代旧偏好，例如 resume.tone")
    reason: str = Field(default="", max_length=200, description="依据：引用用户原话")


class RememberPreferenceTool(Tool):
    name = "remember_preference"
    description = ("当用户表达了长期有效的偏好时调用，把它记入长期记忆。"
                   "一次性的修改要求不要记。用户没有明确授权时只会生成待确认的提议。")
    args_model = RememberArgs
    scopes = frozenset({"memory:write"})
    side_effect = "write"
    max_calls = 2

    def run(self, args: RememberArgs, ctx: ToolContext) -> ToolResult:
        if ctx.memory is None or not ctx.spec.memory.write_namespaces:
            return ToolResult(ok=False, error_code="memory_disabled", message="本任务不允许写入长期记忆")
        item = ctx.memory.preferences.propose(
            ctx.user_id, ctx.spec.memory.write_namespaces[0], args.value, key=args.key,
            explicit=ctx.allow_writes, source="tool", evidence=args.reason)
        if item is None:
            return ToolResult(ok=False, error_code="invalid_value", message="偏好内容太短")
        return ToolResult(ok=True, data={"status": item.status, "id": item.id},
                          message="已生效" if item.status == "active" else "已生成待用户确认的提议",
                          events=[{"type": "memory", "item": item.as_dict()}])
