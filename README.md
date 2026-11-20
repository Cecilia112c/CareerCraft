# CareerCraft · AI 求职助手（研究生小组作业）

上传简历 / 手动填写资料 → 用书签收藏职位，形成“我的职位库”，并用技能需求词云看清岗位要求 → 按 STAR 法则生成定向简历（在简历上指定范围、给出指令，AI 返回修改结果，逐条替换）→ 与润色过程完全隔离的 AI 面试官进行简历诊断和项目深挖。

执行方案见 [`docs/PLAN.md`](docs/PLAN.md)，Agent 运行时设计见 [`docs/HARNESS.md`](docs/HARNESS.md)，跨 Agent 协作见 [`docs/PLAN-D协作与知识库.md`](docs/PLAN-D协作与知识库.md)。

## 目录

```text
CareerCraft/
├── agents/            # 5 个 Agent（纯 Python，不碰业务数据库/HTTP）
│   ├── harness/       # Agent 运行时：runtime / llm / context / memory / tools / validation / skills / observability
│   ├── skills/        # SKILL.md（STAR 写作、简历局部修改、面试深挖）
│   ├── core/          # 共享 JSON 结构（schemas.py）+ 兼容旧接口的薄包装
│   ├── parser_agent/  # PDF → 资料：按标题识别（规则）/ AI 智能填充
│   ├── jd_agent/      # JD 结构化、匹配打分、技能词云统计（insight.py，纯规则）
│   ├── knowledge_agent/ # 材料片段抽取候选事实，用户确认后才可作为依据
│   ├── resume_agent/  # STAR 生成、选区润色、事实校验、ASU 模板渲染
│   └── interview_agent/ # 诊断、问题树、作答评价、报告（输入白名单隔离）
├── backend/app/       # FastAPI：鉴权、资料、岗位、简历版本、面试、任务轮询、定时推送
├── frontend/          # Vue3 + Vite + Element Plus
└── tests/             # pytest（大模型已 mock，不需要 API Key）
```

## 第一次运行（Windows）

需要 Python 3.10+、Node.js 18+。

```powershell
cd D:\project\Resume\CareerCraft

# 1. 后端依赖
conda run -n agent python -m pip install -r requirements.txt
conda run -n agent python -m playwright install chromium

# 2. 配置
copy .env.example .env                       # 然后编辑 .env，填入 LLM_API_KEY、BOCHA_API_KEY
conda run -n agent python -m agents.jd_agent.search_api "后端开发实习 深圳"

# 3. 自测（不需要 API Key）
conda run -n agent python -m pytest -q

# 4. 启动后端（保持这个窗口）
conda run -n agent python -m uvicorn backend.app.main:app --reload --port 8000

# 5. 新开一个窗口启动前端
cd frontend
npm install
npm run dev                                  # 打开 http://localhost:5173
```

演示时也可以只开一个端口：`cd frontend && npm run build`，再启动后端，访问 http://localhost:8000。

旧数据库升级：先停后端，再运行 `conda run -n agent python -m scripts.migrate_plan_d`。脚本先用 SQLite 在线备份，再把旧 PDF 文档复制到资料库；原记录保留。`conda run -n agent python -m scripts.evaluate_plan_d` 可计算逐句依据与补充建议的基线，结果见 [`docs/PLAN-D评测基线.md`](docs/PLAN-D评测基线.md)。

资料库支持 PDF、DOCX、MD、TXT、ZIP、公开 GitHub 仓库与证书。上传后自动抽取候选事实，用户确认后才能用作简历依据。定向简历会先匹配岗位要求；缺少依据时可补充资料或跳过继续。面试可选盲面与对照模式，报告中的证据缺口可形成待补充建议。

## 配置说明（.env）

| 变量 | 说明 |
|---|---|
| `LLM_API_KEY` / `LLM_BASE_URL` | 任意 OpenAI 兼容接口。DeepSeek：`https://api.deepseek.com`；通义千问：`https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `LLM_MODEL_FAST` / `LLM_MODEL_STRONG` | 抽取类任务用 fast，写作和面试用 strong；可以填同一个模型 |
| `LLM_JSON_MODE` | 模型不支持 `response_format=json_object` 时改成 0 |
| `BOCHA_API_KEY` | 博查 Web Search API Key（open.bocha.cn → API KEY 管理）。只填这一项就能用；会通过 `include=zhipin.com` 限定只搜 BOSS 直聘近一周的页面，搜不到时自动放宽到其它招聘网站或不限时间 |
| `SEARCH_PROVIDER` / `TAVILY_API_KEY` | 可选：改用 Tavily |
| `JD_FETCH_DETAIL` | 1 = 尝试抓取岗位详情页（BOSS 通常要求登录，失败会自动退回搜索摘要） |
| `PUSH_TICK_MINUTES` | 每日推送的检查间隔，默认 15 分钟 |

## 演示脚本（也是验收清单）

1. 注册 → “我的资料” → 导入简历 PDF → 先用“按标题识别”，再试“AI 智能填充” → 填入资料并保存。
2. “职位”页 → “安装收藏书签”，把按钮拖到书签栏 → 在自己浏览器里打开 BOSS 职位详情页，点书签收藏 3~5 个职位（也可以“粘贴 JD”，用 `---` 分隔多个）。
3. 职位页上方的“技能需求词云”：
   - “我的职位库”统计收藏的 JD 里各项技能被提到的次数，蓝色是你已具备的，橙色是缺口；点一个词可以筛选下方职位；
   - “市场样本”按求职偏好里的目标职位采集搜索摘要做词频统计，只看词频、不展示职位，所以岗位过期不影响结论。开启“每日刷新”后，每天自动更新一次。
4. 职位详情 → 修改投递进度（已收藏 → 已投递 → 笔试 → 面试 → Offer）→ “生成定向简历”。
5. 简历工坊默认是“指定修改”：在简历上点一个项目（或拖选几句话）→ 右侧写指令，例如“突出高并发，语气更专业。以后都不要用‘负责’开头”→ “让 AI 修改”→ 每条结果可以“替换 / 编辑后替换 / 不用”，鼠标悬停时在简历上预览 → “保存版本”。指令里的“以后都……”会被记成长期偏好，可以在头像菜单的“AI 记忆”页查看。
6. 切到“直接编辑”改几个字（可上传证件照）→ 保存版本 → 导出 PDF / HTML。
7. “更新到我的资料”→ 勾选两条 → 回到资料页确认。
8. “模拟面试”→ 选岗位 + 原始 PDF → 查看诊断 → 回答 3 题（故意答浅一题触发追问）→ 生成报告。
9. 展示 `python -m pytest tests/test_isolation.py -v`：面试 Agent 不 import 其它 Agent，多传任何字段都会被拒绝。

## 设计要点（写报告用）

- **事实不编造**：简历和资料共用同一套带 id 的 JSON 结构。每一句改写都要经过 `resume_agent/check.py` 校验：原文没有的数字和英文技术词会被拦截，并保留原句。
- **指定范围修改**：预览里每个句子带 `data-cc-id`，每个模块带 `data-cc-block`。后端把模块展开成句子，模型只能返回范围内的 id（不合规会触发修复），用户逐条替换后再保存版本。
- **Agent Harness**：统一的运行时，包含长期记忆（用户偏好）、工作记忆（最近对话 + 滚动摘要）、工具白名单与权限范围鉴权、输出校验与修复、运行记录。详见 `docs/HARNESS.md`。
- **职位库 + 词云**：只收录用户亲自确认的职位；技能词云完全由规则统计（同义词归一 + 文档频率），不调用大模型。
- **面试官隔离**：`backend/app/services/interview_input.py` 是唯一组装面试输入的地方，只放 JD、简历纯文本和本场问答；`interview_agent/guard.py` 用 `extra="forbid"` 拒绝任何多余字段；测试会检查 import 关系。
- **分数由代码计算**：岗位匹配分、面试均分、覆盖率、是否追问，都由代码决定。LLM 只给单项评分和文字。
- **合规**：BOSS 直聘没有开放 API。本系统只使用公开搜索引擎的结果，详情页低频访问、遇到登录或验证码就放弃，不绕过任何防护；用户可以手动粘贴 JD。

## 常见问题

- **PDF 导出失败**：先执行 `python -m playwright install chromium`；或者导出 HTML，用浏览器“打印 → 另存为 PDF”。
- **搜索没有结果**：先运行 `python -m agents.jd_agent.search_api "后端开发 深圳"` 检查 `BOCHA_API_KEY`。401 表示 Key 无效，403 表示余额不足；搜索引擎对 BOSS 的收录有延迟，可以换个岗位关键词，或者用“粘贴 JD”。
- **书签点了没反应**：允许招聘网站弹出窗口；确认 CareerCraft 已在运行。书签里写死了当时的访问地址（如 `http://localhost:5173`），换了端口或改用 8000 后要重新拖一次。如果识别出的文字不对，先用鼠标选中 JD 文字再点书签。
- **博查 API Key**：在 open.bochaai.com 用手机验证码登录，到控制台的“API KEY 管理”里创建。
- **模型输出格式错误**：换一个更强的模型，或者把 `LLM_JSON_MODE` 设为 0 再试。
- **数据位置**：`backend/data/`（SQLite 数据库、上传的 PDF）。删除这个目录即可重置。
