"""Read-only, user-scoped knowledge search for resume polishing."""

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from agents.harness.context.prompts import data_block
from agents.harness.tools import Tool, ToolContext, ToolResult
from backend.app.db import engine
from backend.app.knowledge.retrieval import search_chunks


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=2, max_length=100)


class SearchKnowledgeTool(Tool):
    name = "search_knowledge"
    description = "检索当前用户上传的资料片段。结果仅供理解，不能当作未经确认的简历事实。"
    args_model = SearchArgs
    scopes = frozenset({"kb:read"})
    side_effect = "read"
    max_calls = 2

    def run(self, args: SearchArgs, ctx: ToolContext) -> ToolResult:
        if not ctx.user_id.isdigit():
            return ToolResult(ok=False, error_code="owner_required", message="必须有已登录用户")
        with Session(engine) as session:
            rows = search_chunks(session, int(ctx.user_id), args.query, limit=5)
        data = [{"chunk_id": row.id, "text": row.text[:800]} for row in rows]
        return ToolResult(ok=True, data=data_block("knowledge", data))
