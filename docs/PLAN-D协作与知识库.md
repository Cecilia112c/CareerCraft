# PLAN-D：多 Agent 显式协作 + 用户知识库 + 反馈闭环

> 日期：2026-11-18 ｜ 状态：D0–D8 已实施（2026-11-19 验收）；下文保留原始设计与验收清单。
> 基于你的草案（显式交接产物 / 反馈闭环 / 工作流记录 / 补充资料）和对当前代码的检查。
> 与已有文档的关系：`HARNESS.md` 讲“一次模型调用怎么跑”，本文讲“多个 agent 怎么分工、交接、形成闭环”；`ROADMAP-面向Agent岗.md` 里的评测、流式、RAG 等仍然有效，本文的知识库就是那里 RAG 部分的具体落地。

### 实施验收记录（2026-11-19）

- D0–D2：清理线索运行时代码；统一重任务并发上限为 2；落地 AgentCard、上下文契约、带血缘的版本化产物、四条工作流及步骤时间线。失败步骤只允许按顺序重试；进程重启后按步骤恢复四条工作流中的中断节点。
- D3–D4：支持 PDF、DOCX、MD、TXT、ZIP、GitHub 与证书；上传后异步解析、屏蔽密钥、切块和索引；候选事实必须经用户确认才升为 L1。旧 PDF 已通过迁移脚本导入，原记录保留。
- D5–D6：岗位要求与 L1 依据匹配；定向写作、逐句引用与依据校验；缺口卡片可回答、上传或忽略；资料更新后产物失效，用户可检查并逐条采纳修改。简历写回资料库前会产生可审阅的 `ProfileUpdateProposal`。
- D7–D8：面试白名单投影、盲面/对照模式、结构化 findings、待确认的反馈建议与再面一轮对比；重复拒绝触发偏好提议；本地评测脚本和基线见 `PLAN-D评测基线.md`。
- 验证：`agent` 环境中 `pytest -q` 为 90 passed；前端 `npm run build` 成功。当前开发库只有 Plan D 前的 4 份简历版本，131 条旧句子没有逐句引用，因此线上引用正确率尚无新版本样本，评测脚本保持该指标为空值，不把旧数据补造为新依据。

---

## 0. 先回答两个问题

### 0.1 共用一套 harness 和多 agent 有什么区别？

它们是两个层面的东西，不冲突：

| | Harness（运行时） | 多 Agent（组织结构） |
|---|---|---|
| 解决的问题 | **一次模型调用怎么跑**：上下文怎么拼、记忆怎么读、工具怎么鉴权、输出怎么校验 | **谁负责什么、彼此怎么交接**：职责边界、输入输出契约、协作顺序、失败时谁兜底 |
| 类比 | 操作系统 / Web 框架 | 部门分工 / 微服务之间的接口 |
| 现在的状态 | 比较完整（`agents/harness/`） | **几乎没有**：agent 只是几组 `AgentSpec` + 函数，靠后端直接互相喂数据库字段 |

多个微服务共用同一套框架，依然是多个服务；反过来，就算每个 agent 各写一套运行时，如果它们之间没有契约，那也只是“一个大程序拆成了几个函数”。所以**共用 harness 是对的**，它保证了权限、校验、审计、记忆的一致性。真正缺的是 harness 之上的一层：

```text
 ┌──────────── 协作层（本方案新增）────────────┐
 │ AgentCard 能力声明 · 交接产物 Artifact · 工作流引擎 · 产物血缘 · 反馈闭环 │
 └────────────────────────────────────────────┘
 ┌──────────── 运行时层（已有 harness）────────────┐
 │ invoke() · context · memory · tools · validation · runs │
 └────────────────────────────────────────────┘
```

### 0.2 JD agent 是不是不需要很多上下文？

判断是对的。不过现状其实已经比较轻：`jd.normalize` 只看岗位页面原文，不读记忆，预算 10k。真正的问题是：

1. **没有契约说明它“不该看什么”**：轻是碰巧轻，以后有人往里加个人资料也不会被拦住；
2. **产物混在一起**：`Job.data` 里同时放着 JD 结构化结果、个人匹配分、偏好判断（`matched / missing / pref_notes`）。“岗位本身的事实”和“我与岗位的关系”没有分开；
3. **要求没有 id 和出处**：下游无法说“我满足了第 3 条要求，依据是原文第几句”。

所以要做的是给 JD agent 一份**最小上下文契约**，并让它产出带 id、带出处的 `JobBrief`（见 §2.3）。

---

## 1. 现状诊断（对照代码）

| # | 问题 | 代码位置 | 影响 |
|---|---|---|---|
| D1 | agent 之间没有交接契约，靠后端直接读写数据库字段 | `routers/resumes.py` 把 `job_posting(job_row)` 直接传给 `generate_resume`；`interview_input.py` 把简历压成纯文本 | 看不清“谁提供了什么、下游用了什么”；改一处容易连锁出错 |
| D2 | 产物没有版本、来源和生成时间 | `Job.data`、`ResumeVersion.data`、`Interview.gap_report` 都是裸 JSON | 无法判断数据是否过期；无法回放；资料改了，简历和面试也不会提示 |
| D3 | “岗位要求 ↔ 我的经历”的对应关系从未显式计算 | 简历生成只按关键词粗排项目；JD 匹配页只比关键词 | 写简历时不知道哪条要求缺证据；面试官也只能凭整段文字判断 |
| D4 | 事实来源只有资料表单 | `check.py` 的参照只有 `full_text(profile)` | 用户上传的项目代码、证书、文稿都不能作为写简历的依据 |
| D5 | 材料只支持 PDF，只用于解析和面试 | `routers/profile.py` 里 `upload_document` 限制 `%PDF` | 不支持 docx、zip、GitHub，没有知识库 |
| D6 | “信息不足”是一次性文字 | `PolishOutput.needs_confirmation: list[str]` | 用户看完就丢，无法跟踪、补充、回流 |
| D7 | 面试结果不回流 | `FinalReport.suggestions` 只是文字 | 发现某项技能证据不足后，无法驱动资料补充和简历更新 |
| D8 | 运行记录只到“单次模型调用”这一层 | `AgentRun` 没有 workflow / step 的概念 | 用户看不到“JD 已解析 → 依据已匹配 → 问题已生成”的过程，排错也难 |
| D9 | 资料修改不会让下游失效 | 改了资料后，旧简历毫无提示 | 简历可能和最新事实不一致 |
| D10 | 长期记忆的触发规则只有“以后 / 记住”这类关键词 | `memory/extract.py` | 用户反复否定同一种写法时，系统学不到；同时也要防止材料内容误入记忆 |
| D11 | 遗留代码 | `routers/leads.py`、`today.py` 里的线索逻辑，前端已经不用 | 增加理解成本 |
| D12 | 重任务直接放在 `BackgroundTasks` 里 | `services/tasks.py` | 解析 zip 或仓库会占住 Web 进程，需要并发上限 |

---

## 2. 目标设计

### 2.1 Agent 角色与 AgentCard

保持“共用 harness、多角色分工”。在现有 4 个 agent 的基础上，把 `parser_agent` 扩展成 `knowledge_agent`，并新增一个**非 LLM 的协调器**：

| 角色 | 职责 | 是否调用模型 |
|---|---|---|
| **Coordinator**（协调器） | 按工作流定义调度 agent、传递产物、处理等待用户确认的节点 | ❌ 确定性代码（理由见下） |
| **JD Agent** | 岗位原文 → `JobBrief` | ✅ 小模型 |
| **Knowledge Agent**（原 parser） | 材料入库后抽取“候选事实” → `EvidenceClaim`；PDF 解析成资料表单 | ✅ 小模型（解析部分规则优先） |
| **Resume Agent** | `JobBrief` + 知识库 → `ResumeEvidence`（逐条要求匹配依据）→ `ResumeDraft`；局部修改；发现缺口时产出 `MaterialRequest` | ✅ 强模型 |
| **Interview Agent** | 只接收白名单投影 `InterviewBrief` → 诊断、提问、评价、`InterviewReport` | ✅ 强模型 |
| **Feedback**（反馈抽取） | `InterviewReport` → `MaterialRequest` 提议 | 规则为主，可选小模型 |

**为什么协调器不用 LLM（Supervisor）？** 求职流程的顺序是确定的，用 LLM 来调度只会增加不确定性和成本，而且很难评测。确定性的编排加上 LLM 执行节点，是目前工业界更主流的做法；面试时也更容易讲清楚。以后要做“一句话帮我准备投字节”时，可以加一个 Planner 节点生成工作流参数，但执行仍然交给引擎。

**AgentCard**（`agents/<name>/card.py`）：每个 agent 声明自己的能力，协调器和前端都读它。

```python
AgentCard(
    name="jd",
    description="把岗位原文结构化为 JobBrief",
    consumes=(),                         # 不消费任何上游产物，只读原文
    produces=("JobBrief",),
    specs=("jd.brief",),
    context_contract=ContextContract(    # 最小上下文契约：声明“能看什么、不能看什么”
        allowed_materials=("job_page",),
        forbidden=("profile", "knowledge", "memory", "resume"),
        max_input_tokens=6000,
    ),
    tools=(), memory_namespaces=(),
)
```

harness 在 `invoke()` 时检查：传入的 materials 名称必须在 `allowed_materials` 里，否则直接拒绝调用。这样“轻上下文”就从约定变成了强制。

### 2.2 交接产物（Artifact）

**统一信封**（所有产物共用）：

```python
class ArtifactMeta(BaseModel):
    artifact_id: str            # "art_xxx"
    kind: str                   # JobBrief / ResumeEvidence / ...
    schema_version: str         # "1"
    version: int                # 同一主体（如同一个 job_id）下的第几版
    subject: dict               # {"job_id": 12} / {"resume_id": 3, "job_id": 12}
    owner_user_id: int
    produced_by: dict           # {"agent": "jd", "spec_id": "jd.brief", "run_id": "...", "workflow_step_id": ...}
    inputs: list[ArtifactRef]   # 依赖的上游产物（id + version + content_hash）→ 构成血缘图
    sources: list[SourceRef]    # 原始出处：知识库 chunk / 资料字段 / 岗位原文片段
    status: str                 # draft / active / stale / superseded / rejected
    content_hash: str
    created_at: datetime
```

**产物清单**：

| 产物 | 生产者 | 主要内容 | 消费者 |
|---|---|---|---|
| `JobBrief` | JD Agent | 岗位信息；`requirements[]`（`req_id`、要求原文、类别 must/nice、规范化技能、出处原文片段）；职责；岗位级技能集合 | Resume、Interview（投影）、词云 |
| `EvidenceClaim` | Knowledge Agent / 用户 | 一条候选事实：陈述、类型（技能/职责/指标/成果/规模/证书）、出处 chunk、置信度、状态（proposed/confirmed/rejected）、来源级别 | Resume |
| `ResumeEvidence` | Resume Agent（`resume.match`） | 每条 `req_id` → 匹配到的依据列表（资料字段 id 或已确认 claim id）、覆盖程度（strong/partial/none）、理由；缺口列表 | Resume 写作、Interview（投影）、前端“JD 匹配” |
| `ResumeDraft` | Resume Agent | 即现有 `ResumeVersion`，每条句子加上 `evidence_ids`（引用依据） | 导出、Interview（投影） |
| `MaterialRequest` | Resume / Feedback | 待补充资料建议：针对哪条要求或哪个项目、缺什么（指标/职责/技术/规模/成果）、给用户的问题、建议上传的材料类型、优先级、状态 | 前端资料库、Resume（补充后重跑） |
| `InterviewBrief` | 协调器（**代码投影，不调用 LLM**） | 白名单字段：岗位要求列表 + 简历纯文本 + 每条要求在简历中的“声称覆盖”原文引用 | Interview |
| `InterviewReport` | Interview Agent | 现有报告 + `findings[]`（哪条要求、哪道题、证据不足的类型） | Feedback、前端 |
| `ProfileUpdateProposal` | Resume / Feedback | 建议写回资料的改动，需要用户确认 | 资料库 |

**血缘与失效**：
- 每份产物都记录 `inputs`。上游产生新版本，或知识库里被引用的事实被修改/删除时，协调器沿血缘图把下游标记为 `stale`；
- 前端看到 `stale` 时提示“资料已更新，这份简历有 N 处依据过期，[一键检查]”，**不自动重写**；
- 存储：`artifacts` 表放元数据 + JSON 正文；正文较大的（如仓库画像）放文件，表里存路径和哈希。

### 2.3 每个 Agent 的上下文契约

| Agent / 任务 | 允许看到的 | 明确禁止的 | 预算 | 记忆 |
|---|---|---|---|---|
| `jd.brief` | 岗位原文（单页） | 个人资料、知识库、任何记忆 | 6k | 无 |
| `knowledge.extract_claims` | 单个材料的 chunk 批次 + 已有事实摘要（用于去重） | JD、简历、面试 | 8k / 批 | 无 |
| `resume.match` | `JobBrief.requirements` + 检索到的依据（已确认事实优先） | 面试记录、原始仓库全文 | 16k | 读 resume 偏好 |
| `resume.write_project` | 一个项目的资料 + 该项目相关的依据 + 对应的要求 | 其它项目全文、面试 | 16k | 读 resume 偏好 |
| `resume.polish` | 修改范围内的句子 + 这些句子关联的依据 + 检索补充依据 + `JobBrief` 摘要（完整版按需读取） | 面试记录 | 24k | 偏好 + 工作记忆 |
| `interview.*` | 只有 `InterviewBrief` + 本场问答 | 知识库、未确认事实、`MaterialRequest`、润色记录、置信度 | 20k | 只有 interview 命名空间 |

> **关于面试官看到 `ResumeEvidence` 的取舍**：你的草案里面试官接收的是筛选后的 JobBrief 和 ResumeEvidence。我的建议是只投影“招聘方读简历也能得到的东西”：要求列表，以及简历中声称覆盖每条要求的原文引用。**不投影**置信度、未确认事实、待补充建议、真实依据的来源。否则面试官会“提前知道哪里是虚的”，评价就不像真实面试了。另外提供一个开关：盲面模式（默认，只给简历文本）/ 对照模式（给要求 ↔ 简历引用）。

### 2.4 工作流引擎与运行记录

**引擎**（`backend/app/workflows/engine.py`，确定性代码）：
- 工作流 = 有序的节点列表，节点类型有：`agent`（调用某个 spec）、`code`（投影、校验、打分）、`gate`（等待用户确认）；
- 每个节点声明输入产物和输出产物；引擎负责加载输入、调用、保存输出产物、记录步骤；
- 节点失败后可以单独重试；`gate` 节点把工作流置为 `waiting_user`，用户确认后继续；
- 进程重启后，根据步骤状态从断点继续（`running` 超时的步骤重置为 `pending`）。

**四条工作流**：

```text
WF-1 职位入库：   收藏/粘贴 ─▶ [agent] jd.brief ─▶ JobBrief v1
WF-2 定向简历：   JobBrief + 知识库
                 ─▶ [code] 检索依据（每条要求取 top-k）
                 ─▶ [agent] resume.match ─▶ ResumeEvidence
                 ─▶ [gate] 有关键缺口？→ 产出 MaterialRequest，提示用户“补充 / 跳过”
                 ─▶ [agent] resume.write_project × N（并行）
                 ─▶ [code] 依据校验（每句必须引用依据，新数字/技术词必须在依据中）
                 ─▶ ResumeDraft vN
WF-3 模拟面试：   JobBrief + ResumeDraft ─▶ [code] 投影 InterviewBrief ─▶ [agent] diagnose / questions / evaluate…
                 ─▶ InterviewReport ─▶ [code+agent] 反馈抽取 ─▶ MaterialRequest（proposed）
WF-4 资料补充：   上传/回答 ─▶ [code] 入库、切块、建索引 ─▶ [agent] knowledge.extract_claims
                 ─▶ [gate] 用户确认事实 ─▶ [code] 血缘失效（标记 stale）─▶ 提示“更新简历 / 再面一轮”
```

**运行记录**：
- `workflow_runs`：类型、主体、状态（running / waiting_user / done / failed）、开始与结束时间；
- `workflow_steps`：节点名、状态、开始与结束时间、**输入摘要**、**输出摘要**、输入/输出产物引用、关联的 `agent_run_id` 列表、错误信息；
- 摘要用规则生成，不调用 LLM，例如“读取 JobBrief v2（12 条要求）”“匹配结果：强 5 / 部分 4 / 缺失 3，生成 2 条补充建议”；
- 现有 `AgentRun` 加上 `workflow_step_id`，从时间线可以一直钻取到单次模型调用的工具审计和上下文清单。

### 2.5 用户知识库

**材料类型与处理方式**：

| 类型 | 支持格式 | 提取方式 | 切块 |
|---|---|---|---|
| 简历 | PDF、DOCX | 现有 PyMuPDF 规则 + `python-docx` | 按章节和条目 |
| 文稿 | PDF、DOCX、MD、TXT | 文本提取 | 按标题和段落，约 400 字一块、50 字重叠 |
| 证书 | PDF、图片（先只存元数据和文件，OCR 放到以后） | 用户填写名称、机构、日期 | 一条证书一块 |
| 项目代码 | ZIP | 安全解压（见下） → 生成**仓库画像** | README 分段 + 关键文件摘要 + 目录树 |
| GitHub 仓库 | URL | 公开 API：README、语言占比、topics、最近提交（可选填 Token 读私有仓库） | 同上 |
| 备注 | 文本 | 用户直接输入，例如对某个问题的回答 | 一条一块 |

**仓库画像（`RepoProfile`，纯代码生成，不调用 LLM）**：语言占比（按行数）、依赖清单（`package.json` / `requirements.txt` / `pom.xml` / `go.mod`）推断出的框架、目录结构（两层）、模块列表、测试与 CI 是否存在、README 摘要、提交作者统计（仅 GitHub，用于判断“是不是本人主要贡献”）。之后再由 Knowledge Agent 基于画像加 README 抽取候选事实，例如“使用 FastAPI 和 SQLModel 实现后端，包含 JWT 鉴权”。

**安全**（上传的材料一律视为不可信）：
- 大小上限：单文件 20MB，zip 解压后总量 100MB、最多 3000 个文件、单文件 2MB；拒绝路径穿越（`..`、绝对路径）和符号链接；
- 忽略 `node_modules`、`.git`、`dist`、`build`、`venv`、二进制文件、图片、锁文件；
- **密钥扫描**：入库前用正则屏蔽 `.env`、私钥、`sk-…`、`AKIA…`、各类 token 等，替换为 `[REDACTED]`，并在材料详情里提示“已屏蔽 N 处疑似密钥”；
- 材料内容永远包在 `<data:knowledge>` 里，README 中写着“忽略之前的指令”也不会生效；
- 每个用户有存储配额（例如 500MB）；删除材料时，级联删除 chunk、索引、由它产生的待确认事实，并让引用它的产物失效。

**索引**：
- 第一阶段用 **SQLite FTS5**（BM25），不引入新服务，中文用 jieba 分词后写入；
- 第二阶段可选加 `bge-small-zh` 向量做混合检索（对应 ROADMAP 的 P3），检索接口保持不变。

### 2.6 事实分级：什么能写进简历

| 级别 | 来源 | 能否直接写进简历正文 |
|---|---|---|
| L1 已确认事实 | 资料表单字段、用户确认过的 `EvidenceClaim`、用户在“待补充”中直接回答的内容 | ✅ 可以，并作为校验参照 |
| L2 待确认事实 | 从材料中抽取但用户还没确认的 claim | ❌ 不能写进正文；只能出现在“建议补充”里，并附带“确认后可用” |
| L3 原始材料片段 | 知识库 chunk | ❌ 只能用来帮助模型理解上下文，不能直接作为依据 |

- 简历里每句话都要带 `evidence_ids`，并且只能引用 L1；
- `check.py` 升级为 `verify_grounded()`：新文本中的数字和技术词必须出现在**被引用的那几条依据**里，而不是整份资料里，校验更严格；
- 前端在简历上悬停某句话时，显示它的依据卡片（来源材料、原文片段、确认时间）。

### 2.7 资料补充：上下文顺序与 token 预算

以 `resume.polish`（24k 输入预算）为例，按顺序排列：

| 顺序 | 槽位 | 信任级别 | 预算 | 裁剪优先级 |
|---|---|---|---|---|
| 1 | kernel + 任务提示 + skills | authoritative | ≈4,000 | skills 最先裁 |
| 2 | 输出 schema + 工具说明 | authoritative | ≈1,500 | 必需 |
| 3 | 用户长期偏好 | user_confirmed | ≤600 | 60 |
| 4 | 工作记忆（本简历最近几轮 + 摘要） | derived | ≤1,200 | 40 |
| 5 | `JobBrief` 摘要（相关要求 + 技能） | external | ≤1,500 | 65 |
| 6 | 修改范围内的句子 + 所属项目元信息 | user_confirmed | ≤3,000（超出时分批） | 必需 |
| 7 | **L1 依据**（与范围、要求相关，按相关度排序） | user_confirmed | ≤5,000 | 80（最后才裁） |
| 8 | **L3 补充片段**（检索 top-k，标注“仅供理解，不可作为依据”） | external_untrusted | ≤4,000 | 50 |
| 9 | 本次指令 | user_asserted | 不截断，永远在最后 | 必需 |

- 完整 JD、完整仓库画像放在 `lazy_materials` 里，模型需要时调用 `get_material` 读取（渐进式披露）；
- 检索查询 = 范围内句子 + 用户指令 + 相关要求原文；每条要求最多取 3 个依据，总量受预算约束；
- 新增一个工具 `search_knowledge(query, kind?)`，由后端注册（因为它要读数据库），需要 `kb:read` 权限，只有 resume agent 有；每次最多调用 2 次，返回结果同样包在 `<data:knowledge>` 里。

### 2.8 信息不足时的处理：MaterialRequest

**谁会产出**：
- `resume.match`：某条 must 要求的覆盖程度为 none 或 partial；
- `resume.write_project` / `resume.polish`：想写结果但没有数字、想写规模但没有依据（替代现在的 `needs_confirmation` 字符串）；
- 反馈抽取：面试报告中某项技能证据不足。

**结构**：

```python
class MaterialRequest(BaseModel):
    request_id: str
    target: dict                  # {"req_id": "r3"} 或 {"project_id": "p1"} 或 {"skill": "Kafka"}
    gap_type: Literal["metric", "ownership", "tech", "outcome", "scale", "certificate", "other"]
    question: str                 # 给用户看的问题：“订单服务优化后，P99 延迟具体降到了多少？”
    suggested_materials: list[str]  # ["压测报告截图", "项目 README", "周报"]
    priority: Literal["high", "medium", "low"]
    origin: dict                  # {"artifact": "ResumeEvidence v2"} / {"interview_id": 5, "qid": "q3"}
    status: Literal["proposed", "open", "answered", "uploaded", "dismissed", "resolved"]
```

**用户的三种处理方式**：
1. **直接回答**：在卡片里输入一句话 → 成为 L1 事实（来源 = 用户回答，自动确认，因为是用户本人说的）；
2. **上传材料**：触发 WF-4 → 抽取 → 用户确认 → L1；
3. **忽略**：标记 dismissed，同一缺口 30 天内不再提示。

**去重**：同一目标、同一缺口类型只保留一条，新来源合并到 `origin` 里，避免刷屏。

### 2.9 反馈闭环：面试 → 补充 → 简历 → 再面试

```text
InterviewReport.findings
  └─ 反馈抽取（规则：维度均分 ≤ 2 且与某条要求相关；evidence 维度低）
      └─ MaterialRequest（status = proposed，来源 = 面试 #5 第 3 题）
          └─ 用户在面试报告页或资料库确认 → open / 忽略 → dismissed
              └─ 用户回答或上传 → L1 事实
                  └─ 血缘失效：ResumeEvidence、ResumeDraft 标记 stale
                      └─ 用户点“更新简历”→ WF-2 只重跑受影响的要求和项目，结果以修改卡片呈现，逐条替换
                          └─ “用同一岗位再面一轮”→ WF-3；报告页显示两轮对比（覆盖率、各维度均分）
```

**防止误写事实的规则**（用代码保证）：
- 面试中一次答得差，**永远不会**直接改资料或事实，只会生成 `proposed` 状态的建议；
- 面试回答里提到的新事实（“我其实还用了 Kafka”），只会生成“是否加入资料？”的提议，用户确认后才成为 L1；
- 反馈建议不会写入长期记忆。

### 2.10 长期记忆的边界

| 内容 | 去哪里 | 是否进入长期记忆 |
|---|---|---|
| 上传的材料、仓库、证书 | 知识库 | ❌ 永不 |
| 从材料抽取的事实 | `EvidenceClaim`（需确认） | ❌ |
| 对待补充问题的回答 | L1 事实 | ❌（这是事实，不是偏好） |
| “以后都……”“记住……” | 长期偏好 | ✅ 立即生效（已有） |
| 用户连续 3 次拒绝同类改写（如都把“主导”改回“参与”） | 长期偏好 | ⚠️ 生成**待确认**提议：“似乎你不希望夸大角色，要记住吗？” |
| 关于材料的偏好（“公司内部项目名不要写进简历”） | 长期偏好 | ✅ 用户明确表达时 |
| 本次会话上传了哪些材料、回答了哪些问题 | 工作记忆（只记引用和一句话，不记内容） | 会话内 |

**原则**：**知识库存“关于你的事实”，长期记忆存“你希望 AI 怎么做”**，两者永不混用，也分开管理和删除。

### 2.11 其它需要完善的地方

| 优先级 | 事项 |
|---|---|
| 高 | 删除遗留的线索代码（`routers/leads.py`、`Lead` 表、`today.py` 中的线索部分），前端同步清理 |
| 高 | 新增重任务的并发控制：入库和抽取放进独立线程池（并发上限 2），任务表增加 `kind` 维度的排队 |
| 高 | 用户注销或删除资料时级联删除：知识库文件、chunk、事实、产物、工作流记录、记忆 |
| 中 | 评测集增加：依据引用正确率、L2 误用率（未确认事实被写进正文的比例）、补充建议的命中率 |
| 中 | `AgentRun` 增加 `workflow_step_id`，“AI 记忆”页的运行记录可以按工作流分组 |
| 中 | JD 解析结果按原文哈希缓存，同一 JD 不重复调用 |
| 低 | 证书图片 OCR；PPT 文稿；仓库代码的函数级切块 |

---

## 3. 前端改造

### 3.1 “我的资料”→“我的资料库”

顶部 4 个标签页：

1. **结构化资料**：现有表单不变；每个项目旁边显示“关联材料 N · 已确认事实 M”，点击展开。
2. **材料库**：
   - 拖拽上传区（多文件：PDF / DOCX / MD / TXT / ZIP）+ “添加 GitHub 仓库”输入框 + “添加证书”表单；
   - 列表按类型显示图标、名称、大小、状态（排队中 / 解析中 / 已入库 / 失败）、chunk 数、抽取出的事实数、“已屏蔽 N 处密钥”提示；
   - 点击打开详情抽屉：文本预览、仓库画像卡片（语言条形图、框架标签、目录树）、抽取出的事实列表、“关联到项目”下拉。
3. **待确认事实**：每条显示陈述、类型标签、来源材料和原文片段（高亮），操作：确认 / 编辑后确认 / 拒绝；支持批量确认同一材料的事实。
4. **待补充**：`MaterialRequest` 卡片列表，按优先级排序，显示来源（“来自：投字节后端的简历匹配”/“来自：第 2 场面试第 3 题”），操作：直接回答 / 上传材料 / 忽略。

### 3.2 简历工坊

- 新增“依据”视图：悬停句子时显示依据卡片；没有依据的句子用虚线下划线标出；
- 右侧新增“信息不足”区：本简历相关的 `MaterialRequest` 卡片，可以直接回答，回答后提示“可以重新修改这几句”；
- `stale` 横幅：“资料已更新，4 处依据过期。[检查并更新]”→ 结果以修改卡片呈现；
- 新标签页“工作流”：嵌入时间线组件（见 3.4）。

### 3.3 职位详情

- 用 `JobBrief` 展示：要求逐条列出（must / nice 标签、原文出处）；
- 生成过 `ResumeEvidence` 后，每条要求旁边显示覆盖状态（强 / 部分 / 缺失）和依据数量，缺失项可以一键生成补充建议。

### 3.4 工作流时间线组件 `WorkflowTimeline.vue`

```text
● JD 已解析            12:01  1.8s   输入：岗位原文 2,341 字   输出：JobBrief v1（12 条要求，必需 7 条）   [展开]
● 依据已匹配            12:02  6.4s   输入：JobBrief v1 + 已确认事实 38 条   输出：强 5 / 部分 4 / 缺失 3
◐ 等待你补充资料        12:02          产出 2 条补充建议   [去补充] [跳过，继续生成]
○ 改写项目（3 个）
○ 依据校验
```

- 展开后显示：输入与输出摘要、产物版本链接、关联的模型调用（迭代次数、工具调用、token、耗时），失败节点显示错误和“重试此步”；
- 出现在职位详情、简历工坊、面试页、首页“最近的工作流”。

### 3.5 面试报告页

- 新增“证据不足的地方”区：列出 findings，每条可以“生成补充建议”（变成 proposed 的 `MaterialRequest`）；
- 完成补充并更新简历后，显示“用同一岗位再面一轮”；第二轮报告展示与上一轮的对比。

---

## 4. 数据模型（新增与修改）

| 表 | 关键字段 | 说明 |
|---|---|---|
| `knowledge_sources` | id, user_id, kind（resume/doc/certificate/repo_zip/github/note）, title, filename, path, url, size, sha256, status（queued/processing/ready/failed）, error, meta(JSON：仓库画像、证书信息、屏蔽数), linked_project_ids(JSON), created_at | 材料 |
| `knowledge_chunks` | id, source_id, user_id, ord, text, meta(JSON：标题路径、文件路径、行号), token_count | 切块 |
| `knowledge_fts` | FTS5 虚拟表（chunk_id, user_id, text） | 全文检索 |
| `evidence_claims` | id, user_id, statement, claim_type, source_chunk_ids(JSON), project_id, status（proposed/confirmed/rejected）, level（L1/L2）, origin（extracted/user_answer/interview）, confidence, confirmed_at | 事实 |
| `artifacts` | id, user_id, kind, schema_version, version, subject(JSON), produced_by(JSON), inputs(JSON), sources(JSON), status, content_hash, body(JSON), created_at | 交接产物 |
| `material_requests` | id, user_id, target(JSON), gap_type, question, suggested_materials(JSON), priority, origin(JSON), status, resolution(JSON), created_at, updated_at | 待补充 |
| `workflow_runs` | id, user_id, kind, subject(JSON), status, started_at, finished_at | 工作流 |
| `workflow_steps` | id, run_id, name, node_type, status, input_summary, output_summary, input_refs(JSON), output_refs(JSON), agent_run_ids(JSON), error, started_at, finished_at | 步骤 |
| 修改 `Job` | 增加 `brief_artifact_id` | 指向当前 JobBrief |
| 修改 `ResumeVersion` | 增加 `evidence_artifact_id`；句子 `evidence_ids` 存在 data 里 | 依据 |
| 修改 `Interview` | 增加 `brief_artifact_id`、`round`、`previous_interview_id` | 多轮对比 |
| 修改 `Document` | 迁移为 `knowledge_sources`（kind = resume），保留旧表只读兼容 | |

继续沿用 `db.py` 的 `_ADDED_COLUMNS` 补列，新表由 `create_all` 创建；`scripts/migrate_plan_d.py` 负责把旧 `Document` 迁移成知识库材料，执行前先备份数据库。

---

## 5. 接口（新增）

```text
# 知识库
POST   /api/knowledge/sources                 上传文件（多文件，multipart）→ 每个文件一个 task
POST   /api/knowledge/sources/github          {url, token?} → task
POST   /api/knowledge/sources/note            {title, text}
GET    /api/knowledge/sources?kind=
GET    /api/knowledge/sources/{id}            详情（预览、画像、事实）
PATCH  /api/knowledge/sources/{id}            {title, linked_project_ids}
DELETE /api/knowledge/sources/{id}            级联删除并触发失效
GET    /api/knowledge/search?q=             调试与前端预览用
GET    /api/knowledge/claims?status=proposed
POST   /api/knowledge/claims/{id}/confirm     {statement?（编辑后确认）}
POST   /api/knowledge/claims/{id}/reject
POST   /api/knowledge/claims/batch            {ids, action}

# 待补充
GET    /api/material-requests?status=open
POST   /api/material-requests/{id}/answer     {text} → 生成 L1 事实
POST   /api/material-requests/{id}/attach     {source_id}
POST   /api/material-requests/{id}/confirm    （proposed → open）
POST   /api/material-requests/{id}/dismiss

# 产物与工作流
GET    /api/artifacts/{id}                    含血缘（inputs）与下游
GET    /api/jobs/{id}/brief
POST   /api/resumes/{id}/evidence             运行 resume.match → task
POST   /api/resumes/{id}/refresh              只重跑过期部分 → 返回修改卡片
GET    /api/workflows?subject=resume:3
GET    /api/workflows/{id}                    含步骤、摘要、关联 run
POST   /api/workflows/{id}/resume             从 gate 节点继续
POST   /api/workflows/{id}/steps/{sid}/retry

# 面试反馈
POST   /api/interviews/{id}/findings/{fid}/request   生成补充建议
POST   /api/interviews/{id}/next-round
```

---

## 6. 代码目录

```text
agents/
├── harness/
│   ├── spec.py                    # + ContextContract（allowed_materials / forbidden / max_input_tokens）
│   ├── runtime.py                 # + 在 invoke() 时校验 ContextContract；AgentRun 记录 workflow_step_id
│   └── tools/registry.py          # + 支持后端在启动时注册外部工具（如 search_knowledge）
├── contracts/                     ★ 交接产物定义（纯 pydantic，不碰数据库）
│   ├── meta.py                    #   ArtifactMeta / ArtifactRef / SourceRef
│   ├── job.py                     #   JobBrief / Requirement
│   ├── evidence.py                #   EvidenceClaim / ResumeEvidence / RequirementMatch
│   ├── requests.py                #   MaterialRequest / ProfileUpdateProposal
│   ├── interview.py               #   InterviewBrief（白名单投影）/ Finding
│   └── cards.py                   #   AgentCard / ContextContract
├── jd_agent/
│   ├── card.py                    ★
│   ├── specs.py                   #   + jd.brief（输出 JobBrief，要求带 id 和出处）
│   └── brief.py                   ★ #   技能规范化（复用 insight.LEXICON）、出处定位
├── knowledge_agent/               ★ （由 parser_agent 扩展而来，parser 保留为兼容别名）
│   ├── card.py
│   ├── specs.py                   #   knowledge.extract_claims
│   ├── extract.py                 #   分批抽取候选事实、去重
│   └── prompts/extract_claims.md
├── resume_agent/
│   ├── card.py                    ★
│   ├── specs.py                   #   + resume.match；write/polish 输出 evidence_ids 和 MaterialRequest
│   ├── match.py                   ★ #   要求 ↔ 依据匹配
│   ├── grounding.py               ★ #   verify_grounded()（取代 check.py，check.py 保留为子函数）
│   └── prompts/match.md           ★
├── interview_agent/
│   ├── card.py                    ★
│   └── guard.py                   #   InterviewInput 改为接收 InterviewBrief
└── feedback/                      ★ 面试 → 补充建议（规则为主）
    └── extract.py

backend/app/
├── knowledge/                     ★ 知识库（涉及文件和数据库，所以放后端）
│   ├── storage.py                 #   文件存储、配额、删除级联
│   ├── extractors/                #   pdf.py / docx.py / text.py / zip_repo.py / github.py
│   ├── safety.py                  #   zip 安全、文件过滤、密钥屏蔽
│   ├── repo_profile.py            #   仓库画像（语言、依赖、目录、测试/CI）
│   ├── chunker.py                 #   按类型切块
│   ├── index.py                   #   FTS5 + jieba；之后可加向量
│   └── retrieval.py               #   按要求或范围检索、按事实级别排序
├── workflows/                     ★ 协调器
│   ├── engine.py                  #   节点执行、gate 等待、重试、断点恢复
│   ├── definitions.py             #   WF-1 ~ WF-4
│   ├── artifacts.py               #   产物存取、版本、血缘、失效传播
│   ├── projections.py             #   InterviewBrief 等白名单投影（唯一出口）
│   └── summaries.py               #   输入/输出摘要（规则生成）
├── agent_tools/                   ★ 后端注册给 harness 的工具
│   └── knowledge_search.py        #   search_knowledge（需要 kb:read 权限）
├── routers/
│   ├── knowledge.py               ★
│   ├── material_requests.py       ★
│   ├── workflows.py               ★
│   └── artifacts.py               ★
└── services/agent_runtime.py      #   AGENT_SCOPES 增加 kb:read；启动时注册 agent_tools

frontend/src/
├── views/
│   ├── KnowledgeView.vue          ★ （替代 ProfileView，内含 4 个标签页；ProfileView 变为其中的表单组件）
│   ├── ResumeStudioView.vue       #   + 依据视图、信息不足区、stale 横幅、工作流标签页
│   ├── JobsView.vue               #   + JobBrief 要求列表与覆盖状态
│   └── InterviewRoomView.vue      #   + 证据不足区、再面一轮、两轮对比
├── components/knowledge/          ★ UploadZone / SourceList / SourceDrawer / RepoProfileCard / ClaimReview / MaterialRequestCard
├── components/workflow/           ★ WorkflowTimeline / StepDetail / ArtifactBadge
└── components/resume/             ★ EvidencePopover / GapPanel / StaleBanner

scripts/migrate_plan_d.py          ★
tests/
├── test_contracts.py              ★ 产物信封、血缘、失效传播
├── test_context_contract.py       ★ JD agent 传入禁止的资料时拒绝调用
├── test_knowledge_ingest.py       ★ zip 安全（穿越、炸弹、符号链接）、密钥屏蔽、仓库画像、切块
├── test_retrieval.py              ★ FTS 检索、事实级别排序
├── test_grounding.py              ★ 只能引用 L1、L2 不能进正文
├── test_workflow_engine.py        ★ gate 等待与继续、步骤重试、断点恢复
├── test_feedback_loop.py          ★ 面试差答不会改事实，只会生成提议
└── fixtures/knowledge/            ★ 样例 zip、docx、带密钥的 .env、恶意 README
```

---

## 7. 分阶段执行计划

| 阶段 | 内容 | 验收标准 | 估时（人日） | 依赖 |
|---|---|---|---|---|
| **D0 清理** | 删除线索遗留代码；跑通现有测试；任务并发控制 | `pytest` 全绿；职位页、首页功能不受影响 | 1 | — |
| **D1 契约与产物** | `agents/contracts/`、`artifacts` 表、产物存取与血缘、AgentCard、ContextContract 校验；`jd.brief` 输出 JobBrief | 新收藏的职位生成 JobBrief v1，要求带 id 和出处；给 JD agent 传个人资料时被拒绝 | 3 | D0 |
| **D2 工作流引擎与时间线** | 引擎、步骤记录、摘要、`AgentRun` 关联；WF-1 接入；`WorkflowTimeline` 组件 | 职位详情能看到“JD 已解析”步骤，展开可见输入输出摘要和模型调用；失败步骤可重试 | 3 | D1 |
| **D3 知识库入库** | 材料表、提取器（PDF/DOCX/MD/TXT/ZIP/GitHub）、安全、仓库画像、切块、FTS5；资料库的“材料库”标签页 | 上传一个项目 zip，得到仓库画像和 chunk；恶意 zip 被拒绝；密钥被屏蔽；删除时级联清理 | 4 | D0 |
| **D4 事实抽取与确认** | `knowledge.extract_claims`、事实分级、“待确认事实”标签页；WF-4 | 上传材料后出现待确认事实，确认后成为 L1；拒绝的不会再出现 | 2 | D3 |
| **D5 依据匹配与有据写作** | `resume.match` → ResumeEvidence；write/polish 引用依据；`verify_grounded()`；`search_knowledge` 工具；新上下文顺序与预算；WF-2；简历工坊依据视图 | 每句话都有依据，悬停可见；L2 事实不会出现在正文；职位详情显示每条要求的覆盖状态 | 4 | D1、D2、D4 |
| **D6 待补充资料** | MaterialRequest 全流程（产出、去重、回答、上传、忽略）；“待补充”标签页；简历工坊“信息不足”区；`stale` 失效与“检查并更新” | 缺数字时出现补充卡片，回答后重新修改能用上新事实；资料改动后简历提示过期 | 3 | D5 |
| **D7 面试反馈闭环** | InterviewBrief 投影（盲面 / 对照模式）；findings；反馈抽取；再面一轮与对比；WF-3 | 面试差答只产生 proposed 建议；补充后更新简历、再面一轮，报告显示两轮对比 | 3 | D5、D6 |
| **D8 记忆细化、评测与文档** | 重复拒绝 → 偏好提议；评测指标（依据引用正确率、L2 误用率）；更新 HARNESS.md、README、演示脚本 | 新测试全绿；评测报告产出基线数字 | 2 | 全部 |

**合计约 25 人日**。按 3～4 人并行大约 2～2.5 周：
- 一人负责 D1 → D2 → D5（协作主线）；
- 一人负责 D3 → D4（知识库）；
- 一人负责前端（D2 时间线、D3/D4 资料库页面、D5/D6 简历工坊）；
- 后期一起做 D6、D7、D8。

**时间不够时**：先砍 GitHub 接入（只留 zip）、两轮对比、重复拒绝 → 偏好提议、对照模式。**D1、D2、D5、D6 不能砍**，它们是“显式协作 + 补充资料”这件事本身。

---

## 8. 演示脚本（新版，也是验收清单）

1. 资料库 → 上传旧简历 PDF、一个项目 zip、一份证书 → 材料库显示仓库画像，“已屏蔽 1 处密钥”；
2. “待确认事实”确认 6 条、拒绝 1 条；
3. 收藏一个 BOSS 职位 → 职位详情显示 JobBrief（12 条要求），时间线显示“JD 已解析”；
4. 生成定向简历 → 时间线依次出现“依据已匹配（强 5 / 部分 4 / 缺失 3）→ 等待补充资料”→ 回答一条（“P99 从 2.1s 降到 350ms”），跳过另一条 → 继续生成；
5. 简历工坊悬停句子看依据；指定一个项目让 AI“突出成果”，结果引用了刚补充的数字；
6. 模拟面试（盲面模式）→ 报告指出“Kafka 相关经历证据不足”→ 生成补充建议 → 上传设计文档 → 确认事实；
7. 简历提示“2 处依据过期”→ 检查并更新 → 逐条替换 → 再面一轮 → 报告显示两轮对比；
8. 打开某个工作流，展开每一步的输入输出和模型调用，说明“谁提供了什么、下游用了什么”。

---

## 9. 需要你拍板的事项

1. **面试官默认看什么**：建议默认“盲面模式”（只看简历文本），可切换到“对照模式”（加上要求 ↔ 简历引用）。你的草案是给面试官看筛选后的 ResumeEvidence，我建议改成只投影简历引用，理由见 §2.3。
2. **GitHub 接入范围**：只支持公开仓库，还是允许填 Token 读私有仓库？（Token 只在当次请求中使用，不保存）
3. **检索方案**：先用 SQLite FTS5（零依赖），还是一步到位上向量检索？建议先 FTS5，评测后再决定。
4. **上传限制**：单文件 20MB、zip 解压后 100MB、每人 500MB，是否合适？
5. **用户直接回答待补充问题**：是否自动视为已确认事实（L1）？建议是，因为是用户本人陈述；但在依据卡片上标注“来源：你的回答”。
