"""AgentRuntime.invoke(): the single entry point that runs a model for any agent.

  1. resolve memory (long-term preferences + working memory) according to spec.memory
  2. compute visible tools = spec whitelist ∩ request whitelist ∩ granted scopes
  3. compile context slots → messages (+ manifest)
  4. bounded model/tool loop (iterations, tool calls, repairs)
  5. validate output (syntax → schema → domain), bounded repair
  6. write back: explicit preferences, working memory turn, episode
  7. record AgentRun (always, also on failure)
"""

from __future__ import annotations

import json
import logging
import os
import threading

from agents.harness.context.builder import ContextBuilder, Slot
from agents.harness.context.prompts import data_block, kernel_prompt, load_prompt
from agents.harness.errors import AgentError, BudgetExhausted, ValidationFailed
from agents.harness.llm.base import LLMProvider
from agents.harness.memory.manager import MemoryContext, MemoryManager
from agents.harness.memory.models import WorkingTurn
from agents.harness.memory.store import SQLiteMemoryStore
from agents.harness.observability.runs import AgentRun, RunRecorder
from agents.harness.request import ExecutionContext, InvocationRequest, InvocationResult
from agents.harness.skills.loader import Skill, SkillCatalog
from agents.harness.spec import AgentSpec
from agents.harness.tools import ToolContext, ToolExecutor, ToolPolicy, ToolRegistry, default_registry
from agents.harness.tools.base import Tool
from agents.harness.tools.executor import observation_text
from agents.harness.validation.pipeline import validate_output

log = logging.getLogger("careercraft.harness")

SUMMARY_PROMPT = ("把下面的对话压缩成不超过 200 字的中文摘要：保留用户提出的修改要求和偏好、已经完成的修改、"
                  "尚未解决的问题；不要编造。只输出摘要正文。")


class AgentRuntime:
    def __init__(self, provider: LLMProvider | None = None, store: SQLiteMemoryStore | None = None,
                 tools: ToolRegistry | None = None, skills: SkillCatalog | None = None):
        if provider is None:
            from agents.harness.llm.openai_provider import OpenAIProvider
            provider = OpenAIProvider()
        self.provider = provider
        self.store = store or SQLiteMemoryStore(":memory:")
        self.memory = MemoryManager(self.store, summarizer=self._summarize_turns)
        self.tools = tools or default_registry()
        self.skills = skills or SkillCatalog()
        self.policy = ToolPolicy()
        self.executor = ToolExecutor(self.policy)
        self.builder = ContextBuilder()
        self.recorder = RunRecorder(self.store)

    # ------------------------------------------------------------------ helpers
    def _summarize_turns(self, previous: str, turns: list[WorkingTurn]) -> str:
        text = (f"已有摘要：{previous}\n" if previous else "") + "\n".join(
            f"[{'用户' if t.role == 'user' else '助手'}] {t.content}" for t in turns)
        resp = self.provider.complete([{"role": "system", "content": SUMMARY_PROMPT},
                                       {"role": "user", "content": data_block("dialogue", text)}],
                                      tier="fast", json_mode=False, temperature=0.2)
        return resp.content

    def _slots(self, req: InvocationRequest, mem: MemoryContext, visible: dict[str, Tool],
               skills: list[Skill]) -> list[Slot]:
        spec = req.spec
        slots = [Slot("kernel", kernel_prompt(), trust="authoritative", required=True),
                 Slot("agent_prompt", load_prompt(spec.prompt, req.variables), trust="developer", required=True)]
        for s in skills:
            slots.append(Slot(f"skill:{s.name}", f"## 方法（Skill：{s.name}）\n{s.body}", trust="developer",
                              priority=30, max_tokens=2500))
        lazy = [n for n in spec.lazy_materials if n in req.materials] if "get_material" in visible else []
        if visible:
            lines = [f"- {t.name}：{t.description}" for t in visible.values()]
            if lazy:
                lines.append(f"可用资料（需要时用 get_material 读取）：{', '.join(lazy)}")
            slots.append(Slot("tool_protocol", "## 可用工具\n" + "\n".join(lines), trust="authoritative",
                              required=True))
        schema = json.dumps(spec.output.model_json_schema(), ensure_ascii=False)
        if len(schema) < 6000:
            slots.append(Slot("output_schema", "## 输出 JSON Schema（必须严格符合）\n" + schema,
                              trust="authoritative", required=True))
        slots.append(Slot("preferences", mem.render_preferences(), trust="user_confirmed", priority=60,
                          max_tokens=800))
        slots.append(Slot("working_memory", mem.render_working(), trust="derived", priority=40, max_tokens=1200))
        for name, content in req.materials.items():
            if name in lazy:
                continue
            slots.append(Slot(f"material:{name}", data_block(name, content), role="user",
                              trust="external_untrusted", priority=70))
        if req.instruction.strip():
            slots.append(Slot("instruction", "【本次指令】\n" + req.instruction.strip(), role="user",
                              trust="user_asserted", required=True))
        return slots

    # ------------------------------------------------------------------ invoke
    def invoke(self, req: InvocationRequest) -> InvocationResult:
        spec, ctx = req.spec, req.ctx
        if spec.context_contract:
            contract = spec.context_contract
            unexpected = set(req.materials) - set(contract.allowed_materials)
            forbidden = set(req.materials) & set(contract.forbidden)
            if unexpected or forbidden:
                raise ValueError(f"{spec.id}: materials outside context contract: {sorted(unexpected | forbidden)}")
            if contract.allowed_variables is not None:
                extra_variables = set(req.variables) - set(contract.allowed_variables)
                if extra_variables:
                    raise ValueError(f"{spec.id}: variables outside context contract: {sorted(extra_variables)}")
        run = AgentRun(user_id=ctx.user_id, agent=spec.agent, spec_id=spec.id, spec_version=spec.version,
                       session=ctx.session, workflow_step_id=ctx.workflow_step_id, tier=spec.tier)
        events: list[dict] = []
        try:
            mem = self.memory.prepare(ctx.user_id, spec.agent, ctx.session, spec.memory)
            run.memory = {"preferences": len(mem.preferences), "working_turns": len(mem.working.turns),
                          "has_summary": bool(mem.working.summary)}
            visible = self.policy.visible(spec, ctx, self.tools)
            run.visible_tools = list(visible)
            skills = self.skills.load(spec.skills) if spec.skills else []
            run.skills = [{"name": s.name, "sha": s.sha} for s in skills]
            messages, manifest = self.builder.build(self._slots(req, mem, visible, skills),
                                                    spec.budget.max_input_tokens)
            run.manifest = manifest.as_dict()

            output = self._loop(req, messages, visible, run, events)

            if spec.memory.write_namespaces and "memory:write" in ctx.scopes:
                for item in self.memory.capture_explicit(ctx.user_id, spec.memory, req.instruction):
                    events.append({"type": "memory", "item": item.as_dict()})
            summary = ""
            if spec.summarize:
                try:
                    summary = spec.summarize(output) or ""
                except Exception:  # noqa: BLE001
                    log.exception("summarize failed for %s", spec.id)
            if spec.memory.record_working and ctx.session:
                self.memory.record_turn(ctx.user_id, spec.agent, ctx.session, req.instruction, summary)
            if ctx.user_id != "anonymous":
                self.memory.record_episode(ctx.user_id, spec.agent, spec.id, ctx.session,
                                           summary or spec.description or spec.id, "ok")
            data = run.finish("ok")
            self.recorder.record(data)
            return InvocationResult(output=output, run=data, memory_events=events)
        except Exception as exc:
            data = run.finish("failed", f"{type(exc).__name__}: {exc}")
            self.recorder.record(data)
            if isinstance(exc, AgentError):
                raise
            raise AgentError(str(exc)) from exc

    def _loop(self, req: InvocationRequest, messages: list[dict], visible: dict[str, Tool], run: AgentRun,
              events: list[dict]):
        spec, ctx = req.spec, req.ctx
        tool_ctx = ToolContext(user_id=ctx.user_id, spec=spec, session=ctx.session, scopes=ctx.scopes,
                               allow_writes=ctx.allow_writes, materials=req.materials, memory=self.memory)
        schemas = [t.schema() for t in visible.values()] or None
        counts: dict[str, int] = {}
        tools_open = bool(visible)
        repairs = 0
        for iteration in range(spec.budget.max_iterations):
            run.iterations = iteration + 1
            resp = self.provider.complete(messages, tier=spec.tier, tools=schemas,
                                          tool_choice="auto" if tools_open else "none",
                                          json_mode=not schemas, temperature=spec.budget.temperature)
            run.model = resp.model or run.model
            run.add_usage(resp.usage)

            if resp.tool_calls and tools_open:
                messages.append({"role": "assistant", "content": resp.content or None, "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                    for c in resp.tool_calls]})
                for call in resp.tool_calls:
                    result, audit = self.executor.execute(call, visible, ctx, spec, tool_ctx, counts)
                    run.tool_calls.append(audit)
                    events.extend(result.events)
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": observation_text(result)})
                if sum(counts.values()) >= spec.budget.max_tool_calls:
                    tools_open = False
                    messages.append({"role": "user", "content": "工具调用次数已用完，请根据已有信息直接输出最终 JSON。"})
                continue
            if resp.tool_calls:          # 工具已关闭但模型仍想调用：提醒直接作答
                messages.append({"role": "user", "content": "现在不能再调用工具，请直接输出最终 JSON。"})
                continue

            report = validate_output(resp.content, req)
            if report.ok:
                return report.output
            if repairs >= spec.budget.max_repairs:
                raise ValidationFailed("模型输出未通过校验：" + "；".join(report.issues[:3]))
            repairs += 1
            run.repairs = repairs
            messages += [{"role": "assistant", "content": resp.content},
                         {"role": "user", "content": report.repair_message()}]
        raise BudgetExhausted(f"达到模型调用次数上限（{spec.budget.max_iterations}）仍未得到合格输出")


# ---------------------------------------------------------------------- global runtime
_runtime: AgentRuntime | None = None
_lock = threading.Lock()


def configure(**kwargs) -> AgentRuntime:
    """Backend calls this at startup (memory db path, provider). Tests pass a ScriptedProvider."""
    global _runtime
    with _lock:
        if "store" not in kwargs and kwargs.get("memory_path"):
            kwargs["store"] = SQLiteMemoryStore(kwargs.pop("memory_path"))
        kwargs.pop("memory_path", None)
        _runtime = AgentRuntime(**kwargs)
        return _runtime


def get_runtime() -> AgentRuntime:
    global _runtime
    with _lock:
        if _runtime is None:
            _runtime = AgentRuntime(store=SQLiteMemoryStore(os.getenv("AGENT_MEMORY_DB") or ":memory:"))
        return _runtime


def reset_runtime() -> None:
    global _runtime
    with _lock:
        _runtime = None


def invoke(spec: AgentSpec, *, variables: dict | None = None, materials: dict | None = None,
           instruction: str = "", ctx: ExecutionContext | None = None) -> InvocationResult:
    return get_runtime().invoke(InvocationRequest(spec=spec, variables=variables or {}, materials=materials or {},
                                                  instruction=instruction, ctx=ctx or ExecutionContext()))
