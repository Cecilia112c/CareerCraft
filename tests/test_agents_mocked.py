"""End-to-end agent logic through the harness with a scripted LLM (no API key needed)."""

from pathlib import Path

from agents.core import runner
from agents.core.schemas import JobPosting, ProfileData, ResumeDoc
from agents.harness import ExecutionContext, get_runtime
from agents.interview_agent import Question, evaluate_answer, validate_input
from agents.resume_agent import generate_resume, polish_selection, render_html
from agents.resume_agent.specs import HeadlineOut
from tests.test_schemas import PROFILE

RESUME_CTX = ExecutionContext.for_user(1, session="resume:1",
                                       scopes={"material:read", "memory:read", "memory:write"})


def test_legacy_run_json_repairs_once(llm):
    llm.push("not json", {"headline": "x", "summary": "y"})
    out = runner.run_json(Path(__file__).parents[1] / "agents/resume_agent/prompts/headline.md",
                          {"job": "{}"}, HeadlineOut)
    assert out.headline == "x"
    assert len(llm.calls) == 2                                   # 第一次格式错误，修复一次


def test_generate_keeps_facts(llm):
    rewrite = {"background": [{"id": "b1", "text": "大促期间订单接口延迟高，影响下单体验"}],
               "responsibilities": [{"id": "", "text": "基于 Redis 设计缓存层"},
                                    {"id": "", "text": "引入 Kafka 异步削峰"}],   # Kafka 是编造的
               "impact": [], "keywords": ["Redis", "Kafka"]}
    llm.push(rewrite, {"headline": "后端开发实习生", "summary": "具备 Go 与 Redis 的订单服务开发经验"})
    job = JobPosting(title="后端开发", keywords=["Go", "Redis", "Kafka"])
    out = generate_resume(ProfileData.model_validate(PROFILE), job, job_id=1)
    proj = out.resume.experience[0].projects[0]
    texts = [b.text for b in proj.responsibilities]
    assert "基于 Redis 设计缓存层" in texts
    assert not any("Kafka" in t for t in texts)          # 编造内容被拦截
    assert "Kafka" not in proj.keywords
    assert out.warnings
    assert "star-writing" in llm.calls[0]["messages"][0]["content"] or "STAR" in llm.calls[0]["messages"][0]["content"]
    html = render_html(out.resume, interactive=True)
    assert "dataset.ccId" in html and "dataset.ccBlock" in html


def test_polish_out_of_scope_id_triggers_repair(llm):
    doc = ResumeDoc.model_validate(PROFILE)
    bad = {"patches": [{"id": "b1", "new_text": "大促期间订单接口延迟过高"},
                       {"id": "basic.summary", "new_text": "不该被修改"}]}
    good = {"patches": [{"id": "b1", "new_text": "大促期间订单接口延迟过高", "reason": "更简洁"}]}
    llm.push(bad, good)
    out = polish_selection(doc, ProfileData.model_validate(PROFILE), ["b1"], "custom", "更简洁一些", None,
                           ctx=RESUME_CTX)
    assert [p.id for p in out.patches] == ["b1"]
    assert out.patches[0].reason == "更简洁"
    assert "不在修改范围内" in llm.calls[1]["messages"][-1]["content"]   # 修复消息带上了领域校验错误


def test_polish_block_scope_expands_to_project_items(llm):
    doc = ResumeDoc.model_validate(PROFILE)
    llm.push({"patches": []})
    out = polish_selection(doc, ProfileData.model_validate(PROFILE), ["p1"], "star", "", None, ctx=RESUME_CTX)
    assert set(out.scope) >= {"b1"} and len(out.scope) == 2         # 背景 b1 + 一条职责
    user_msg = llm.calls[0]["messages"][-1]["content"]
    assert "<data:selected" in user_msg and "【本次指令】" in user_msg


def test_polish_records_working_memory_and_explicit_preference(llm):
    doc = ResumeDoc.model_validate(PROFILE)
    llm.push({"patches": [{"id": "b1", "new_text": "大促期间订单接口延迟过高"}]})
    out = polish_selection(doc, ProfileData.model_validate(PROFILE), ["b1"], "custom",
                           "改短一点。以后都不要用“负责”开头", None, ctx=RESUME_CTX)
    assert out.memory_events and out.memory_events[0]["item"]["status"] == "active"
    mem = get_runtime().memory
    view = mem.working.view("1", "resume", "resume:1")
    assert [t.role for t in view.turns] == ["user", "assistant"]
    # 下一次调用：长期偏好和工作记忆都会进入上下文
    llm.push({"patches": []})
    polish_selection(doc, ProfileData.model_validate(PROFILE), ["b1"], "custom", "再专业一点", None, ctx=RESUME_CTX)
    system = llm.calls[-1]["messages"][0]["content"]
    assert "不要用“负责”开头" in system and "本会话的工作记忆" in system


def test_interview_follow_up_rule(llm):
    inp = validate_input({"job": {"title": "后端"}, "resume_text": "某科技 后端实习 订单服务 Redis 缓存 P99 2.1s→350ms",
                          "history": []})
    q = Question(qid="q1", project="订单服务优化", level=2, question="为什么用 Redis？")
    llm.push({"scores": {"correctness": 2, "depth": 1, "ownership": 2, "evidence": 1, "consistency": 3},
              "comment": "回答较浅", "follow_up": "你说“用了缓存”，具体缓存了哪些数据？"})
    ev = evaluate_answer(inp, q, "用了缓存，速度变快了", follow_ups_so_far=0)
    assert ev.next_action == "follow_up" and ev.average == 1.8
    assert llm.calls[0]["tools"] == []                        # 面试官没有任何工具
