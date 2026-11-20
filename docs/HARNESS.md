# CareerCraft Agent Harness 设计说明

> 代码位置：`agents/harness/`。四个 agent（parser / jd / resume / interview）的所有模型调用都只走一个入口：`AgentRuntime.invoke()`。

## 1. 目录结构

```text
agents/
├── harness/                     # 通用运行时（不含任何业务逻辑）
│   ├── spec.py                  # AgentSpec / MemoryPolicy / Budget：每个任务的静态策略
│   ├── request.py               # InvocationRequest / ExecutionContext / InvocationResult
│   ├── runtime.py               # AgentRuntime.invoke()：唯一的模型执行入口
│   ├── errors.py
│   ├── prompts/kernel.md        # 所有 agent 共用的最高优先级规则
│   ├── llm/                     # 模型提供方
│   │   ├── base.py              #   LLMProvider 接口（OpenAI 风格消息 + function calling）
│   │   ├── openai_provider.py   #   DeepSeek / 通义 / Kimi / OpenAI
│   │   └── fake.py              #   ScriptedProvider：测试与离线演示
│   ├── context/                 # 上下文工程
│   │   ├── builder.py           #   槽位 → 消息，按优先级裁剪，生成 manifest
│   │   ├── budget.py            #   token 估算与截断
│   │   └── prompts.py           #   模板填充、<data:...> 不可信资料包装
│   ├── memory/                  # 记忆
│   │   ├── store.py             #   SQLite 存储（独立文件 backend/data/agent_memory.db）
│   │   ├── longterm.py          #   长期记忆：用户偏好（提议→确认→生效→被替代/遗忘）
│   │   ├── working.py           #   工作记忆：最近轮次 + 滚动摘要（按会话隔离）
│   │   ├── extract.py           #   识别“以后/记住/不要再…”这类长期偏好
│   │   ├── manager.py           #   MemoryManager 门面
│   │   └── models.py
│   ├── tools/                   # 工具
│   │   ├── base.py              #   Tool 契约：参数 schema、权限范围、副作用、调用上限、超时
│   │   ├── registry.py          #   注册表（拒绝不安全的工具定义）
│   │   ├── policy.py            #   鉴权：白名单 ∩ 权限范围 ∩ 频率 ∩ 归属 ∩ 写入确认
│   │   ├── executor.py          #   解析 → 鉴权 → 校验 → 超时执行 → 审计
│   │   └── builtin/             #   get_material / recall_preferences / remember_preference
│   ├── validation/pipeline.py   # 语法 → 结构 → 领域校验，生成修复提示
│   ├── skills/loader.py         # SKILL.md 目录、预加载、hash
│   └── observability/runs.py    # AgentRun 运行记录（不含正文）
├── skills/                      # SKILL.md：star-writing / resume-polish / interview-deep-dive
├── parser_agent/  specs.py + agent.py + prompts/
├── jd_agent/      specs.py + agent.py + prompts/ + insight.py（技能词云，纯规则）
├── resume_agent/  specs.py + agent.py + prompts/ + check.py（事实校验）
└── interview_agent/ specs.py + agent.py + guard.py（输入白名单）+ prompts/
```

## 2. 一次调用的生命周期

```text
backend 路由
  └─ agent_ctx(user, agent, session, instruction)     ← 唯一授予权限的地方（services/agent_runtime.py）
      └─ agent 函数（如 polish_selection）组装 variables / materials / instruction
          └─ harness.invoke(SPEC, ...)
              1. memory.prepare()        按 spec.memory 读长期偏好 + 本会话工作记忆
              2. policy.visible()        spec.tools ∩ ctx.tool_allowlist ∩ 已注册 ∩ 权限范围
              3. skills.load()           预加载 SKILL.md
              4. builder.build()         槽位 → messages + manifest（超预算按优先级裁剪）
              5. 模型/工具循环            ≤ max_iterations 次模型调用，≤ max_tool_calls 次工具调用
              6. validate_output()       语法 → pydantic 结构 → spec.validators；不合格最多修复 max_repairs 次
              7. 写回                    显式偏好 → 长期记忆；本轮摘要 → 工作记忆；情景记录
              8. recorder.record()       AgentRun（成功或失败都记）
```

## 3. 上下文槽位（固定顺序）

| 顺序 | 槽位 | 信任级别 | 是否必需 | 裁剪优先级 |
|---|---|---|---|---|
| system | kernel.md | authoritative | 是 | — |
| system | agent prompt（填充变量后） | developer | 是 | — |
| system | skills | developer | 否 | 30（最先裁） |
| system | 可用工具 + 可按需读取的资料 | authoritative | 是 | — |
| system | 输出 JSON Schema | authoritative | 是 | — |
| system | 【用户长期偏好】 | user_confirmed | 否 | 60 |
| system | 【本会话的工作记忆】 | derived | 否 | 40 |
| user | `<data:xxx>` 资料 | external_untrusted | 否 | 70（最后裁） |
| user | 【本次指令】 | user_asserted | 是 | 永远在最后，不截断 |

- 规则最前、当前指令最后，降低 lost-in-the-middle 的影响。
- 必需槽位本身超过预算时，**不调用模型**，直接报 `ContextBudgetExceeded`。
- `lazy_materials`（例如完整 JD）不预加载，只在系统提示里列出名称，模型需要时调用 `get_material` 读取（渐进式披露）。

## 4. 记忆

| 层 | 内容 | 生命周期 | 写入规则 |
|---|---|---|---|
| 长期记忆（偏好） | “英文技术名词保持原文”“不要以‘负责’开头” | 跨会话，直到用户删除 | 用户说“以后/记住/不要再…” → 立即生效；模型通过工具提出 → **待确认**；同一 key 新值替代旧值；删除 = forgotten |
| 工作记忆 | 本简历 / 本场面试最近的指令和结果 | 按会话（`resume:<id>`、`interview:<id>`） | 每轮自动记录；超过 12 轮把较早的轮次压缩成摘要（大模型摘要，失败时退回抽取式） |
| 情景记录 | 每次任务的一句话结果 | 跨会话 | 运行时自动写入 |

**命名空间隔离**：`global / resume / jd / interview / parser`。每个 spec 声明可读、可写的命名空间。面试 agent 只能读写 `interview`，读不到简历润色时的偏好与记录。

前端“AI 记忆”页（`/memory`）可以查看、确认、编辑、删除偏好，并查看最近的运行记录。简历工坊里可以查看或清空这份简历的工作记忆。

## 5. 工具调用鉴权

一次工具调用必须通过全部检查，默认拒绝：

1. **白名单**：`AgentSpec.tools ∩ ExecutionContext.tool_allowlist ∩ 已注册工具`，不可见的工具根本不会发给模型。
2. **权限范围**：`tool.scopes ⊆ ctx.scopes`，权限由后端 `AGENT_SCOPES` 授予：

   | agent | 权限 |
   |---|---|
   | resume | material:read, kb:read, memory:read, memory:write |
   | parser / knowledge / jd | 无 |
   | interview | 无（也没有任何工具） |

3. **频率**：单个工具不超过 `max_calls`，总数不超过 `budget.max_tool_calls`。用完后 `tool_choice=none`。
4. **归属**：注册时拒绝带 `user_id / owner` 等参数的工具；调用时参数里出现这些字段也会被拒绝。归属一律取自 `ExecutionContext`。
5. **参数**：pydantic 校验，`extra="forbid"`。
6. **写入确认**：`side_effect=write` 的工具只有在 `ctx.allow_writes`（用户本轮明确说了“记住/以后…”）时才直接生效，否则只生成待确认的提议。
7. **超时与审计**：线程池执行并设超时；每次调用记录工具名、参数 hash、成功与否、错误码、耗时。

被拒绝的调用以数据形式返回给模型（`{"ok": false, "error_code": "..."}`），不会抛到运行时之外。

## 6. 校验与修复

```text
syntax  → 能否解析出 JSON
schema  → pydantic 输出模型
domain  → spec.validators（例如 resume.polish：输出的 id 必须在修改范围内）
```

不合格时把结构化错误作为修复消息发回模型，最多 `max_repairs` 次。业务层另有确定性校验，例如 `resume_agent/check.py` 会拦截原文没有的数字和技术词，面试的分数由代码计算。

## 7. 运行记录（AgentRun）

保存的内容：spec id/版本、模型、迭代次数、修复次数、可见工具、工具审计、用了几条偏好和几轮工作记忆、上下文 manifest（每个槽位的 token 数、hash、是否被裁剪）、token 用量、耗时、错误。

**不保存**简历正文、联系方式或完整 prompt。

## 8. 如何新增一个 agent 任务

```python
# agents/xxx_agent/specs.py
TASK = AgentSpec(
    id="xxx.task", agent="xxx", prompt=PROMPTS / "task.md", output=TaskOut,
    tools=("get_material",), lazy_materials=("big_doc",),
    memory=MemoryPolicy(read_namespaces=("global",)),
    budget=Budget(max_iterations=3), validators=(my_check,),
)
# agents/xxx_agent/agent.py
out = invoke(TASK, variables={...}, materials={"doc": ..., "big_doc": ...}, instruction=user_text, ctx=ctx).output
```

后端在 `services/agent_runtime.py` 的 `AGENT_SCOPES` 里给新 agent 授权，路由里用 `agent_ctx(...)` 构造上下文。

## 9. 测试

`tests/conftest.py` 为每个测试配置 `ScriptedProvider` + 内存存储，不需要 API Key：

- `tests/test_harness.py`：工具可见性、白名单收窄、渐进式披露、拒绝与审计、归属与参数校验、频率与预算、写入确认、修复、预算耗尽、记忆替代与遗忘、命名空间隔离、工作记忆压缩、上下文裁剪、运行记录不含正文。
- `tests/test_agents_mocked.py`：resume / interview 通过 harness 的端到端流程。

## 10. PLAN-D 协作层

Harness 负责单次调用；`backend/app/workflows/` 负责跨 agent 的确定性顺序、等待用户确认、步骤记录与产物血缘。`agents/contracts/` 定义 JobBrief、ResumeEvidence、InterviewBrief 等交接正文。每次调用带 `workflow_step_id`，可以从时间线追到模型、工具审计和上下文清单。

JD 的 `ContextContract` 只允许岗位原文，不读个人资料或记忆。Knowledge Agent 将材料切块后提出 L2 候选事实；用户确认后才转为 L1。Resume Agent 先按岗位要求检索 L1 依据，再判断覆盖程度；逐句写作由 `verify_grounded()` 检查所引用事实中的数字与技术词。InterviewBrief 由代码投影，盲面默认只看岗位名称与简历，对照模式增加岗位要求和简历原文引用，不传候选事实、来源可信度或润色历史。

资料和岗位更新会使下游产物标记为 `stale`。简历工坊的“检查并更新”返回待审阅的修改卡片，不直接改写已保存版本。反复跳过同一类改写只创建待确认的写作偏好；确认后才成为长期记忆。
