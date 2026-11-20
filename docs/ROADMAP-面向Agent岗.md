# CareerCraft 面向大厂 Agent / AI 全栈岗位的补强方案

> 日期：2026-11-16
> 目标：让 CareerCraft 从“功能齐全的课程作业”变成“面试时能讲 20 分钟、经得起追问的 Agent 工程项目”。

---

## 0. 结论先行

现在的项目**功能面已经够宽**：四个 Agent、记忆、工具鉴权、校验修复、前端完整。但面试官追问时会卡在下面几处：

| 面试官会问 | 现在能答吗 | 缺什么 |
|---|---|---|
| “你这个 Agent 效果怎么样？有数据吗？” | ❌ | **评测体系**：没有评测集，没有任何指标数字 |
| “线上跑起来什么样？给我看看” | ❌ | **从没真正运行过**；没有部署地址、没有演示视频 |
| “一次调用慢在哪、花多少钱？” | ⚠️ 只有本地 AgentRun 记录 | **链路追踪 + 成本看板**（Langfuse / OpenTelemetry） |
| “用户等 30 秒看进度条？” | ⚠️ 轮询 | **流式输出（SSE）**，逐条吐出修改结果 |
| “简历证据怎么检索？资料多了怎么办？” | ⚠️ 把整段原文塞进上下文 | **RAG**：证据切块 + 向量检索 + 重排 |
| “多 Agent 怎么协作？有状态机吗？” | ⚠️ 后端手写串联 | **编排层**：显式状态图、可中断、人工确认节点、断点恢复 |
| “工具能接外部系统吗？知道 MCP 吗？” | ❌ | **MCP 工具适配**，至少接一个 MCP Server |
| “怎么防 prompt 注入？测过吗？” | ⚠️ 有 `<data>` 包装但没测 | **红队测试集** + 注入检测 + 指标 |
| “并发高了怎么办？” | ❌ BackgroundTasks + SQLite | **任务队列**（Redis + arq/Celery）、Postgres |
| “为什么不用 LangChain / LangGraph？” | ⚠️ 自研但没对比 | 一页**选型说明** + 关键节点用 LangGraph 实现一版做对比 |

**排序原则**：先补“能证明效果”的（运行起来 + 评测数字），再补“能体现工程深度”的（流式、追踪、RAG、编排），最后补“锦上添花”的（MCP、队列、多模型路由）。

---

## 1. 详细方案

### 1.1 P0 让它真正跑起来，并且能被别人看到（必须做）

面试官最怕“PPT 项目”。这一阶段不加功能，只做到：

- 本地 `pytest` 全绿，前后端跑通演示脚本的 8 个步骤；
- **Docker Compose 一键启动**（backend + frontend + postgres + redis）；
- **GitHub Actions CI**：lint（ruff、eslint）、pytest、`vite build`、评测冒烟测试；
- 部署到一台云服务器（学生机即可），配 HTTPS 域名；
- 录一个 **3 分钟演示视频**，README 顶部放 GIF；
- README 写清架构图（Mermaid）和关键指标表（指标来自 1.2）。

### 1.2 P1 评测体系（Agent 岗最看重，优先级最高）

“我做了一个 Agent”不稀奇，“我把 X 指标从 A 提到 B”才稀奇。

**评测集**（`evals/datasets/`，JSONL，每类 30～50 条，脱敏）：

| 数据集 | 内容 | 来源 |
|---|---|---|
| resume_polish | 简历句子 + 指令 + 项目事实 + 期望特征 | 组员和同学的真实简历（脱敏），每人出 10 条 |
| fabrication_trap | 诱导编造的指令（“加上提升了 50%”） | 手写 |
| jd_normalize | JD 原文 → 期望的结构化字段 | 收藏的真实 JD |
| parser | PDF → 期望字段 | 10～20 份简历 PDF |
| interview_followup | 问题 + 浅/深两类回答 → 是否该追问 | 手写 |
| injection | JD/简历里藏“忽略以上指令…” | 手写 + 公开注入样本 |

**指标**（每个都要能写进简历）：

| 指标 | 计算方式 | 说明 |
|---|---|---|
| 事实编造率 | 新增数字/技术词/公司的句子占比（规则 + LLM 裁判复核） | 核心卖点，目标接近 0 |
| 指令遵循率 | LLM-as-judge 按评分表打分，人工抽检 20% 校准一致性 | 报告裁判与人工的一致率 |
| 范围越界率 | 输出 id 不在指定范围的比例 | harness 校验前/后对比 |
| JD 字段 F1 | 逐字段比对 | 规则 vs 大模型 |
| 追问决策准确率 | 是否追问与标注一致 | |
| 注入成功率 | 模型执行了注入指令的比例 | 防护前/后对比 |
| P50/P95 延迟、单次成本 | 来自运行记录 | 模型路由前/后对比 |

**做消融实验**（面试时最有说服力的部分）：

- 无 harness 校验 vs 有校验 → 编造率、越界率；
- 有/无 STAR skill 预加载 → 指令遵循分；
- 有/无工作记忆 → 多轮修改的一致性（用户第 3 轮说“别再用负责开头”，第 5 轮是否还遵守）；
- 不同模型（DeepSeek / Qwen / GPT-4o-mini）→ 质量 vs 成本曲线。

**实现**：`evals/runner.py` 复用同一个 `AgentRuntime.invoke()`（评测和线上走同一条路径），结果写 `evals/reports/<date>.json` 和 Markdown 表；CI 里只跑 10 条冒烟子集，防止回退。

### 1.3 P2 流式输出 + 链路追踪 + 成本看板

- **流式**：`invoke_stream()` 产出事件（`thinking / tool_call / tool_result / patch / done`），后端用 SSE 推送，前端逐条渲染修改卡片，首条结果延迟目标 < 3 秒。
- **追踪**：接 Langfuse（可自托管）或 OpenTelemetry。每次调用是一条 trace，模型调用、工具调用、校验、修复都是 span；AgentRun 里加 `trace_id`，“AI 记忆”页可以跳转查看。
- **成本**：按模型单价计算每次调用的费用，后台看板按 agent / 用户 / 天汇总；单用户每日 token 上限（限流）。
- **缓存**：相同输入哈希命中则直接返回（JD 解析、简历抽取最有效）；系统提示前缀保持稳定，以利用服务商的 prompt cache。

### 1.4 P3 RAG：简历证据检索

现在润色时把项目原文整段塞进上下文，资料多了会超预算，也说不出“检索”相关的经验。

- 资料、上传的 PDF、历史简历版本切成**证据块**（按项目/句子），存 `pgvector`；
- Embedding 用 `bge-small-zh` 本地模型或 API；检索 = 向量 + BM25 混合，再用 bge-reranker 重排；
- 润色/生成时，按指令和 JD 要求检索 top-k 证据，作为 `<data:evidence>` 注入，模型输出要带 `evidence_ids`；
- `check.py` 升级为**基于证据的校验**：新文本中的每个事实都要能在被引用的证据里找到；
- 评测：检索 recall@k、引用正确率，对比“整段塞入”方案的 token 消耗和效果。

### 1.5 P4 编排层：显式状态图 + 人工确认

- 用**状态图**描述“定向简历”工作流：`解析 JD → 选证据 → 并行改写各项目 → 校验 → 人工确认 → 保存版本`；
- 节点可重试，状态持久化到 Postgres，进程重启后可以**从断点继续**；
- 人工确认节点（interrupt）：低置信度或命中“需要补充信息”时暂停，等前端确认；
- 实现方式二选一：
  - A. 在自研 harness 上加 `orchestration/graph.py`（几百行，面试能讲清每一行）；
  - B. 用 **LangGraph** 实现同一个流程，写一页对比（代码量、可控性、调试体验）。
  
  推荐 **A 为主、B 做对比实验**：既展示底层理解，又能回答“为什么不用框架”。
- 再加一个**计划型 Agent（Planner）**：用户说“帮我准备投字节后端实习”，由 Planner 拆成“对照 JD 诊断 → 改简历 → 出面试题”多个子任务并调用现有 Agent。注意子 Agent 只有 1 层、权限只能收窄。

### 1.6 P5 MCP 与工具生态

- harness 增加 `tools/mcp_adapter.py`：把 MCP Server 的工具注册进 ToolRegistry，**同样受白名单、权限范围、审计约束**；
- 自己写一个 **CareerCraft MCP Server**，暴露“查询职位库 / 读取简历 / 记录面试题”，让 Claude Desktop 或 Cursor 也能调用；
- 可选：接日历 MCP，自动创建面试提醒。

### 1.7 P6 安全与可靠性

- **注入防护**：外部内容检测（规则 + 小模型分类），命中后降级为“只读、不调工具”；用 1.2 的 injection 集合测出防护前/后的成功率；
- **输出护栏**：PII 检测（手机号、身份证号不能出现在不该出现的字段），敏感属性过滤；
- **可靠性**：模型调用超时、重试、熔断，主模型失败时自动切到备用模型；
- **数据**：用户注销时级联删除所有记忆与运行记录。

### 1.8 P7 工程化扩展

- SQLite → **Postgres**（Alembic 迁移），记忆库合并进同一个库（独立 schema）；
- BackgroundTasks → **Redis + arq**（异步、可重试、可观测的任务队列）；
- 前端补 **Vitest** 单测和 **Playwright** 端到端测试（覆盖演示脚本）；
- 后端加结构化日志（JSON）和 `/metrics`（Prometheus）。

---

## 2. 执行计划（按 3～4 人、5 周估算）

| 周 | 目标 | 交付物（每周末可演示） | 负责 |
|---|---|---|---|
| W1 | **P0 跑起来** | pytest 全绿、演示脚本走通、Docker Compose、CI、部署地址 | 全员（后端 1 人主导部署） |
| W2 | **P1 评测体系** | 6 个数据集首版、`evals/runner.py`、第一份指标报告（基线） | Agent 2 人；前端做“评测报告”页 |
| W3 | **P2 流式 + 追踪 + 成本** + 第一轮消融 | SSE 流式修改、Langfuse trace、成本看板；消融结果表 | 后端 + 前端 + Agent 1 人 |
| W4 | **P3 RAG + P4 编排** | pgvector 证据检索、基于证据的校验、状态图工作流 + 断点恢复；对比实验 | Agent 2 人 + 后端 1 人 |
| W5 | **P5 MCP + P6 安全 + 收尾** | MCP 适配器与 Server、注入测试结果、最终指标报告、视频、简历条目 | 全员 |

**时间不够时的砍法**（从后往前砍）：P7 → P5 → P4 的 LangGraph 对比 → P3 的重排。**P0、P1、P2 不能砍**，它们决定项目能不能被“证明”。

**每周固定动作**：跑一次全量评测，把指标变化记进 `evals/reports/CHANGELOG.md`。到最后，这份记录就是简历和面试里的“迭代故事”。

---

## 3. 代码目录（新增部分用 ★ 标出）

```text
CareerCraft/
├── agents/
│   ├── harness/
│   │   ├── runtime.py              # + invoke_stream()，事件流
│   │   ├── events.py             ★ # 流式事件类型：tool_call / patch / done …
│   │   ├── llm/
│   │   │   ├── router.py         ★ # 按任务/成本/失败自动选择模型，备用模型切换
│   │   │   └── cache.py          ★ # 输入哈希缓存
│   │   ├── orchestration/        ★ # 编排层
│   │   │   ├── graph.py          ★ #   状态图：节点、边、条件分支、interrupt
│   │   │   ├── checkpoint.py     ★ #   状态持久化 / 断点恢复
│   │   │   └── planner.py        ★ #   计划型 Agent，拆子任务（深度 1）
│   │   ├── retrieval/            ★ # RAG
│   │   │   ├── chunker.py        ★ #   资料 / PDF / 简历切块
│   │   │   ├── embedder.py       ★ #   bge-small-zh / API
│   │   │   ├── store.py          ★ #   pgvector + BM25 混合检索
│   │   │   └── rerank.py         ★
│   │   ├── tools/
│   │   │   └── mcp_adapter.py    ★ # MCP 工具接入（受同一套鉴权约束）
│   │   ├── guardrails/           ★ # 注入检测、PII 检测、输出护栏
│   │   └── observability/
│   │       ├── tracing.py        ★ # OpenTelemetry / Langfuse
│   │       └── cost.py           ★ # 单价表与成本计算
│   ├── workflows/                ★ # 业务工作流（用 orchestration 搭建）
│   │   ├── tailored_resume.py    ★ #   JD → 证据 → 并行改写 → 校验 → 人工确认 → 保存
│   │   └── interview_prep.py     ★
│   └── …（现有四个 agent）
├── mcp_server/                   ★ # 对外暴露 CareerCraft 能力的 MCP Server
│   ├── server.py
│   └── tools.py
├── evals/                        ★ # 评测体系
│   ├── datasets/                 #   *.jsonl（脱敏）
│   ├── metrics/                  #   fabrication.py / instruction.py / f1.py / latency_cost.py
│   ├── judges/                   #   LLM-as-judge 评分表与提示词、人工一致性校准
│   ├── runner.py                 #   复用 AgentRuntime.invoke()，支持 --subset / --model / --ablation
│   ├── ablations.yaml            #   消融实验配置
│   └── reports/                  #   每次结果 JSON + Markdown + CHANGELOG.md
├── backend/app/
│   ├── routers/stream.py         ★ # SSE
│   ├── routers/admin.py          ★ # 成本看板、评测报告
│   ├── workers/                  ★ # arq 任务（替代 BackgroundTasks）
│   └── migrations/               ★ # Alembic（Postgres）
├── frontend/src/
│   ├── composables/useStream.ts  ★ # SSE 订阅
│   ├── views/EvalReportView.vue  ★ # 评测指标与消融结果
│   ├── views/AdminCostView.vue   ★
│   └── tests/                    ★ # vitest + playwright
├── deploy/                       ★
│   ├── docker-compose.yml        #   backend / frontend / postgres(pgvector) / redis / langfuse
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── nginx.conf
├── .github/workflows/ci.yml      ★ # lint + pytest + vite build + eval 冒烟
└── docs/
    ├── HARNESS.md
    ├── ARCHITECTURE.md           ★ # 架构图（Mermaid）、数据流、选型理由
    ├── DECISIONS.md              ★ # 自研 harness vs LangGraph、SQLite→Postgres 等决策记录
    └── EVAL.md                   ★ # 评测方法、数据集说明、指标定义
```

---

## 4. 写进简历的样子（做完后，用真实数字替换 X）

> **CareerCraft · AI 求职 Agent 平台**　负责人｜Python · FastAPI · Vue3 · pgvector · Langfuse
> - 设计并实现自研 Agent Harness：统一的模型/工具循环、长期偏好与工作记忆、工具白名单与权限鉴权、输出三级校验与自动修复，支撑简历、JD、面试 4 个 Agent 共 X 个任务。
> - 构建 6 类、共 X 条评测集与 LLM-as-judge 评测流水线（与人工标注一致率 X%）；通过证据检索 + 规则校验，将简历改写的事实编造率从 X% 降到 X%，范围越界率降到 0。
> - 基于 pgvector 混合检索 + 重排实现证据级 RAG，在效果持平的情况下单次上下文 token 减少 X%；接入 SSE 流式输出，首条结果延迟从 Xs 降到 Xs。
> - 用状态图编排“定向简历”工作流，支持人工确认与断点恢复；接入 Langfuse 追踪与成本看板，通过模型路由和缓存将单次成本降低 X%。

**注意**：只写真实测出来的数字。面试官会顺着每个数字追问“怎么测的、基线是什么”，评测报告就是你的底气。

---

## 5. 面试准备清单（和项目一起准备）

- 能画出一次 `invoke()` 的完整时序图，说清每一步为什么存在；
- 能讲清 3 个踩过的坑以及怎么定位的（追踪截图最有说服力）；
- 准备“为什么自研 harness 而不用 LangChain / LangGraph”的回答（附对比实验数据）；
- 准备“记忆怎么防止记错”“工具权限怎么设计”“怎么评测 LLM 输出”这三个高频问题的 2 分钟回答；
- 每个组员都能独立讲完整个系统，再深入讲自己负责的部分。
