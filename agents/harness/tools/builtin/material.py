"""get_material: progressive disclosure of large optional materials (e.g. the full JD).

Only names declared in AgentSpec.lazy_materials and actually supplied in the request can be read.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agents.harness.context.prompts import _to_text
from agents.harness.tools.base import Tool, ToolContext, ToolResult


class GetMaterialArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(description="资料名称，必须是可用资料列表中的一个")


class GetMaterialTool(Tool):
    name = "get_material"
    description = "按名称读取本次任务的可选资料（例如完整 JD、简历大纲）。只能读取“可用资料”中列出的名称。"
    args_model = GetMaterialArgs
    scopes = frozenset({"material:read"})
    side_effect = "read"
    max_calls = 3

    def run(self, args: GetMaterialArgs, ctx: ToolContext) -> ToolResult:
        if args.name not in ctx.spec.lazy_materials or args.name not in ctx.materials:
            return ToolResult(ok=False, error_code="not_found",
                              message=f"可用资料：{[n for n in ctx.spec.lazy_materials if n in ctx.materials]}")
        return ToolResult(ok=True, data=_to_text(ctx.materials[args.name])[:6000])
