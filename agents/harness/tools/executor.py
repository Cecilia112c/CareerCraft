"""Executes one model tool call: parse → authorize → validate → run (with timeout) → audit.

Errors are returned to the model as data ({"ok": false, "error_code": ...}) so it can recover;
they never raise into the runtime loop.
"""

from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from concurrent.futures import TimeoutError as FutureTimeout

from pydantic import ValidationError

from agents.harness.llm.base import ToolCall
from agents.harness.request import ExecutionContext
from agents.harness.spec import AgentSpec
from agents.harness.tools.base import Tool, ToolContext, ToolResult
from agents.harness.tools.policy import ToolPolicy

MAX_OBSERVATION_CHARS = 4000
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tool")


class ToolExecutor:
    def __init__(self, policy: ToolPolicy | None = None):
        self.policy = policy or ToolPolicy()

    def execute(self, call: ToolCall, visible: dict[str, Tool], ctx: ExecutionContext, spec: AgentSpec,
                tool_ctx: ToolContext, counts: dict[str, int]) -> tuple[ToolResult, dict]:
        started = time.perf_counter()
        audit = {"tool": call.name, "args_sha": hashlib.sha256(call.arguments.encode("utf-8")).hexdigest()[:12]}

        def finish(result: ToolResult) -> tuple[ToolResult, dict]:
            audit.update(ok=result.ok, error_code=result.error_code,
                         ms=round((time.perf_counter() - started) * 1000))
            return result, audit

        try:
            raw = json.loads(call.arguments or "{}")
            if not isinstance(raw, dict):
                raise ValueError("arguments must be an object")
        except ValueError as exc:
            return finish(ToolResult(ok=False, error_code="invalid_json", message=str(exc)[:200]))

        decision = self.policy.authorize(call.name, raw, visible, ctx, spec, counts)
        if not decision.allowed:
            return finish(ToolResult(ok=False, error_code=decision.code, message=decision.message))
        counts[call.name] = counts.get(call.name, 0) + 1
        tool = visible[call.name]
        try:
            args = tool.args_model.model_validate(raw)
        except ValidationError as exc:
            msg = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:4])
            return finish(ToolResult(ok=False, error_code="invalid_arguments", message=msg))
        if decision.needs_confirmation:
            tool_ctx = replace(tool_ctx, allow_writes=False)
        future = _pool.submit(tool.run, args, tool_ctx)
        try:
            result = future.result(timeout=tool.timeout_s)
        except FutureTimeout:
            return finish(ToolResult(ok=False, error_code="timeout", message=f"超过 {tool.timeout_s}s"))
        except Exception as exc:  # noqa: BLE001
            return finish(ToolResult(ok=False, error_code="tool_error", message=str(exc)[:200]))
        return finish(result)


def observation_text(result: ToolResult) -> str:
    payload = result.model_dump(exclude={"events"})
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) > MAX_OBSERVATION_CHARS:
        text = text[:MAX_OBSERVATION_CHARS] + "…(truncated)"
    return f'<data:tool_result trust="untrusted">{text}</data:tool_result>'
