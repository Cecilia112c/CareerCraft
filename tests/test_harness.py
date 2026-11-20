"""Harness core: tool authorization layers, memory rules, context budget, run records."""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from agents.harness import AgentSpec, Budget, ExecutionContext, MemoryPolicy, get_runtime, invoke
from agents.harness.context import ContextBuilder, Slot
from agents.harness.errors import BudgetExhausted, ContextBudgetExceeded, ValidationFailed
from agents.harness.llm import tool_call
from agents.harness.memory import WorkingMemory, explicit_preferences
from agents.harness.memory.working import MAX_TURNS
from agents.harness.tools import Tool, ToolRegistry, ToolResult
from agents.harness.errors import ConfigError

PROMPT = Path(__file__).parent / "_prompt.md"


class Out(BaseModel):
    answer: str = ""


@pytest.fixture(autouse=True, scope="module")
def prompt_file():
    PROMPT.write_text("测试任务：{{topic}}", encoding="utf-8")
    yield
    PROMPT.unlink(missing_ok=True)


def spec(**kw) -> AgentSpec:
    base = dict(id="resume.test", agent="resume", prompt=PROMPT, output=Out)
    base.update(kw)
    return AgentSpec(**base)


FULL = ExecutionContext.for_user(7, session="resume:9", scopes={"material:read", "memory:read", "memory:write"})


# ------------------------------------------------------------------ tools
def test_tools_not_visible_without_scope(llm):
    llm.push({"answer": "ok"})
    s = spec(tools=("get_material", "remember_preference"), lazy_materials=("job_detail",))
    ctx = ExecutionContext.for_user(7, scopes={"material:read"})             # 没有 memory:write
    invoke(s, variables={"topic": "x"}, materials={"job_detail": "JD 原文"}, ctx=ctx)
    assert llm.calls[0]["tools"] == ["get_material"]


def test_request_allowlist_narrows_spec(llm):
    llm.push({"answer": "ok"})
    ctx = ExecutionContext.for_user(7, scopes=FULL.scopes, tool_allowlist={"recall_preferences"})
    invoke(spec(tools=("get_material", "recall_preferences")), variables={"topic": "x"}, ctx=ctx)
    assert llm.calls[0]["tools"] == ["recall_preferences"]


def test_get_material_progressive_disclosure(llm):
    s = spec(tools=("get_material",), lazy_materials=("job_detail",))
    llm.push(tool_call("get_material", {"name": "job_detail"}), {"answer": "done"})
    result = invoke(s, variables={"topic": "x"}, materials={"job_detail": "岗位要求：Go", "selected": "句子"}, ctx=FULL)
    first_user = llm.calls[0]["messages"][-1]["content"]
    assert "岗位要求：Go" not in first_user and "<data:selected" in first_user   # job_detail 没有预加载
    tool_msg = llm.calls[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and "岗位要求：Go" in tool_msg["content"]
    assert result.run["tool_calls"][0]["ok"] is True


def test_denied_tool_returns_error_to_model(llm):
    s = spec(tools=("get_material",), lazy_materials=("job_detail",))
    llm.push(tool_call("remember_preference", {"value": "以后用英文"}), {"answer": "done"})
    result = invoke(s, variables={"topic": "x"}, materials={"job_detail": "JD"}, ctx=FULL)
    audit = result.run["tool_calls"][0]
    assert audit["ok"] is False and audit["error_code"] == "tool_not_allowed"
    assert "tool_not_allowed" in llm.calls[1]["messages"][-1]["content"]


def test_owner_override_and_bad_args_rejected(llm):
    s = spec(tools=("get_material",), lazy_materials=("job_detail",))
    llm.push(tool_call("get_material", {"name": "job_detail", "user_id": 1}, "c1"),
             tool_call("get_material", {"nme": "job_detail"}, "c2"), {"answer": "done"})
    result = invoke(s, variables={"topic": "x"}, materials={"job_detail": "JD"}, ctx=FULL)
    codes = [c["error_code"] for c in result.run["tool_calls"]]
    assert codes == ["owner_override_forbidden", "invalid_arguments"]


def test_tool_rate_limit_and_budget(llm):
    s = spec(tools=("get_material",), lazy_materials=("job_detail",), budget=Budget(max_tool_calls=2, max_iterations=4))
    llm.push(tool_call("get_material", {"name": "job_detail"}, "a"), tool_call("get_material", {"name": "job_detail"}, "b"),
             {"answer": "done"})
    result = invoke(s, variables={"topic": "x"}, materials={"job_detail": "JD"}, ctx=FULL)
    assert len(result.run["tool_calls"]) == 2
    assert llm.calls[2]["tool_choice"] == "none"            # 用完预算后不再允许调用工具


def test_write_tool_without_consent_only_proposes(llm):
    s = spec(tools=("remember_preference",), memory=MemoryPolicy(read_namespaces=("resume",), write_namespaces=("resume",)))
    llm.push(tool_call("remember_preference", {"value": "技术名词保留英文", "key": "resume.terms"}), {"answer": "ok"})
    result = invoke(s, variables={"topic": "x"}, ctx=FULL)
    assert result.memory_events[0]["item"]["status"] == "proposed"
    assert get_runtime().memory.preferences.active("7", ["resume"]) == []


def test_registry_rejects_unsafe_tools():
    class Args(BaseModel):
        model_config = ConfigDict(extra="forbid")
        user_id: int

    class Bad(Tool):
        name = "bad_tool"
        description = "x"
        args_model = Args

        def run(self, args, ctx):
            return ToolResult(ok=True)

    with pytest.raises(ConfigError):
        ToolRegistry().register(Bad())


# ------------------------------------------------------------------ loop & validation
def test_validation_failure_after_repairs(llm):
    llm.push("bad", "still bad")
    with pytest.raises(ValidationFailed):
        invoke(spec(), variables={"topic": "x"}, ctx=FULL)
    run = get_runtime().store.list_runs("7")[0]
    assert run["status"] == "failed" and run["repairs"] == 1


def test_budget_exhausted_when_model_keeps_calling_tools(llm):
    s = spec(tools=("get_material",), lazy_materials=("job_detail",), budget=Budget(max_iterations=2, max_tool_calls=5))
    llm.push(tool_call("get_material", {"name": "job_detail"}, "a"), tool_call("get_material", {"name": "job_detail"}, "b"))
    with pytest.raises(BudgetExhausted):
        invoke(s, variables={"topic": "x"}, materials={"job_detail": "JD"}, ctx=FULL)


def test_domain_validator_drives_repair(llm):
    s = spec(validators=(lambda out, req: [] if out.answer == "yes" else ["answer 必须是 yes"],))
    llm.push({"answer": "no"}, {"answer": "yes"})
    assert invoke(s, variables={"topic": "x"}, ctx=FULL).output.answer == "yes"


# ------------------------------------------------------------------ memory
def test_explicit_preference_detection():
    assert explicit_preferences("这句改短一点") == []
    assert explicit_preferences("改短。以后都不要用“负责”开头！") == ["以后都不要用“负责”开头"]
    assert explicit_preferences("请记住：技术名词保留英文") == ["技术名词保留英文"]


def test_supersede_and_forget(llm):
    prefs = get_runtime().memory.preferences
    a = prefs.propose("7", "resume", "语气偏正式", key="resume.tone", explicit=True)
    b = prefs.propose("7", "resume", "语气轻松一些", key="resume.tone", explicit=True)
    assert [p.value for p in prefs.active("7", ["resume"])] == ["语气轻松一些"]
    assert get_runtime().store.get_item(a.id).status == "superseded"
    prefs.forget("7", b.id)
    assert prefs.active("7", ["resume"]) == []
    assert prefs.active("8", ["resume"]) == []                     # 用户隔离


def test_namespace_isolation_for_interview(llm):
    prefs = get_runtime().memory.preferences
    prefs.propose("7", "resume", "简历偏好：英文术语", explicit=True)
    s = AgentSpec(id="interview.test", agent="interview", prompt=PROMPT, output=Out,
                  memory=MemoryPolicy(read_namespaces=("interview",)))
    llm.push({"answer": "ok"})
    invoke(s, variables={"topic": "x"}, ctx=ExecutionContext.for_user(7))
    assert "英文术语" not in llm.calls[0]["messages"][0]["content"]


def test_working_memory_compaction():
    store = get_runtime().store
    wm = WorkingMemory(store, summarizer=lambda prev, turns: f"摘要{len(turns)}轮")
    for n in range(MAX_TURNS + 3):
        wm.append("7", "resume", "resume:1", "user", f"指令{n}")
    view = wm.view("7", "resume", "resume:1", keep_recent=50)
    assert view.summary.startswith("摘要") and len(view.turns) <= MAX_TURNS


def test_summarizer_failure_falls_back_to_extractive():
    store = get_runtime().store

    def boom(prev, turns):
        raise RuntimeError("llm down")

    wm = WorkingMemory(store, summarizer=boom)
    for n in range(MAX_TURNS + 1):
        wm.append("7", "resume", "resume:2", "user", f"要求{n}")
    assert "要求0" in wm.view("7", "resume", "resume:2").summary


# ------------------------------------------------------------------ context
def test_context_budget_trims_optional_and_keeps_instruction_last():
    slots = [Slot("kernel", "规则" * 50, required=True),
             Slot("working_memory", "历史" * 3000, priority=40),
             Slot("material:job", "岗位" * 200, role="user", priority=70),
             Slot("instruction", "【本次指令】改短", role="user", required=True)]
    messages, manifest = ContextBuilder().build(slots, max_input_tokens=1200)
    assert messages[-1]["content"].endswith("【本次指令】改短")
    entry = {e["name"]: e for e in manifest.entries}
    assert entry["working_memory"]["dropped"] or entry["working_memory"]["truncated"]
    assert not entry["material:job"]["dropped"]
    assert manifest.total_tokens <= 1200


def test_required_context_over_budget_does_not_call_model(llm):
    s = spec(budget=Budget(max_input_tokens=50))
    with pytest.raises(ContextBudgetExceeded):
        invoke(s, variables={"topic": "很长" * 200}, ctx=FULL)
    assert llm.calls == []


def test_run_record_has_manifest_and_no_body_text(llm):
    llm.push({"answer": "ok"})
    invoke(spec(), variables={"topic": "x"}, materials={"resume": "张三 13800000000"}, ctx=FULL)
    run = get_runtime().store.list_runs("7")[0]
    assert run["status"] == "ok" and run["manifest"]["entries"]
    assert "13800000000" not in json.dumps(run, ensure_ascii=False)
