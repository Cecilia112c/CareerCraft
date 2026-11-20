# 方案 C：收藏为主、搜索为辅 —— 职位库 + 发现线索

> 版本：v1（设计稿，未实施） ｜ 日期：2026-11-15
> 背景：搜索引擎检索 BOSS 的结果不准（BOSS 收录少，城市不准，收录日期≠发布日期，会出现已下线职位），而且每条结果都要过一遍大模型，又慢又费钱。
> 结论：把“机器检索”和“人工确认”分成两层。**只有用户亲自收藏的职位才进入职位库和后续的 AI 流程**；搜索只负责提供线索。

---

## 0. 设计原则

| 原则 | 落地方式 |
|---|---|
| 准确优先 | 职位库只收用户亲眼看过、主动收藏的职位（书签 / 粘贴 JD） |
| 能用规则就不用大模型 | 书签拿到的是结构化页面，标题、薪资、城市、标签、技能词都用规则取；大模型只在规则拆不开“职责 / 要求”时兜底 |
| 线索零大模型成本 | 搜索结果只做规则过滤和打分，不做解析 |
| 合规 | 不自动登录、不翻页、不批量抓取；书签只读取用户当前打开的这一页，由用户点击触发，由用户确认后才保存 |
| 解析逻辑不放在书签里 | 书签只负责“搬运”页面内容，解析放在 CareerCraft 里。页面结构变了只需要改 CareerCraft 的代码，**不用重新安装书签** |

---

## 1. 从截图看 BOSS 搜索页能拿到什么

你给的截图是 BOSS 的职位搜索页（`zhipin.com/web/geek/job?query=agent&city=...`）。它是**左列表 + 右详情**的双栏结构，这对书签非常友好：

**左侧职位卡片（每张卡都有）**

| 字段 | 示例 |
|---|---|
| 标题 | 大模型Agent业务开发实习生-剪映 |
| 薪资 | 500-550元/天 |
| 标签 | 4天/周 · 4个月 · 本科 |
| 公司 | 字节跳动 |
| 地点 | 深圳·南山区·科技园 |
| 链接 | 卡片里指向 `/job_detail/xxxx.html` 的链接 |

**右侧详情面板（当前选中的那一个职位）**

| 字段 | 示例 |
|---|---|
| 标题、薪资、城市、标签 | 同上，外加“4天/周 4个月 本科” |
| 技能标签 | agent / api调用 / Langchain / 大模型 / Python ← **可以直接当关键词，不用大模型提取** |
| 职位描述全文 | 含“职位描述 / 职位要求”两段、带编号的条目 ← 规则基本就能拆分 |
| 工作地 | base 深圳/广州 |

**这意味着：**

1. 在搜索页点一次书签，就能同时拿到**当前职位的完整 JD**，以及**左侧整页的职位卡片**（通常 15～30 条）。
2. 用户不需要逐个打开详情页：在左侧点一个职位，再点一次书签，就能收藏它的完整 JD。

---

## 2. 整体架构

```text
                    ┌────────────── 发现（低成本、可能不准）──────────────┐
求职偏好 ──每日──▶  │ 搜索 API（只取标题/链接/摘要） → 规则过滤与打分 → 线索 Lead │ ──┐
                    └──────────────────────────────────────────────────┘   │ 用户点“打开原文”
                                                                              ▼
                    ┌──────────────────── 确认（准确）───────────────────┐   招聘网站页面
用户在招聘网站浏览 ──▶│ 书签 v2 → /clip 小窗口 → 站点适配器解析 → 用户勾选确认 │ ◀─┘
                    └──────────────────────────────────────────────────┘
                          │ 卡片（摘要级）            │ 详情（完整 JD）
                          ▼                          ▼
                      线索 Lead                   职位库 Job（投递进度、备注、匹配分）
                                                     │
                                                     ▼
                                      定向简历 / 模拟面试（不变）
```

**两类数据的区别**

| | 线索 Lead | 职位库 Job |
|---|---|---|
| 来源 | 搜索 API、书签批量收藏的列表卡片 | 书签收藏的详情、粘贴 JD、由线索补全详情后转入 |
| 信息完整度 | 摘要级：标题、链接、摘要、薪资、城市 | 完整 JD：职责、要求、技能标签 |
| 是否调用大模型 | 否 | 仅在规则拆不开职责/要求时兜底 |
| 能否生成简历、模拟面试 | 不能（JD 不完整） | 能 |
| 生命周期 | 新线索 → 已忽略 / 已转入职位库 | 已收藏 → 已投递 → 笔试 → 面试 → offer / 未通过 / 已放弃 |

---

## 3. 书签 v2（核心）

### 3.1 书签只负责搬运

书签脚本做的事情尽量少，这样以后几乎不用重新安装：

1. 判断页面大致类型（只用来给 CareerCraft 提示，不做解析）；
2. 复制页面主体内容（`document.body` 的副本），删掉 `script / style / svg / img / iframe / noscript`，上限 1.5 MB；
3. 一起带上：当前网址、页面标题、用户选中的文字、页面纯文本（作为兜底）；
4. 打开 CareerCraft 的 `/clip` 小窗口，用 `postMessage` 把内容发过去（沿用现有的机制）。

**消息格式（v2）：**

```jsonc
{
  "source": "careercraft-clip",
  "version": 2,
  "url": "https://www.zhipin.com/web/geek/job?query=agent&city=101280600",
  "title": "「深圳agent招聘」- BOSS直聘",
  "selection": "",            // 用户选中的文字（有的话最优先）
  "html": "<div …>…</div>",   // 删掉脚本、样式和图片后的页面主体
  "text": "…"                 // 页面纯文本，适配器失败时使用
}
```

### 3.2 CareerCraft 里的站点适配器（解析在这里做）

放在 `frontend/src/clip/adapters/`，用浏览器自带的 `DOMParser` 解析（只解析文本，不会执行页面里的任何脚本）：

```ts
interface ClipAdapter {
  id: 'boss' | 'liepin' | 'shixiseng' | 'campus' | 'generic'
  match(url: URL): boolean
  parse(doc: Document, url: URL): {
    detail: ClipDetail | null      // 当前职位的完整详情
    cards: ClipCard[]              // 列表页上的职位卡片
    pageType: 'search' | 'detail' | 'unknown'
  }
}
interface ClipCard {
  title: string; salary: string; company: string; area: string
  tags: string[]          // 4天/周、4个月、本科…
  url: string             // 详情页链接（统一成规范形式）
}
interface ClipDetail extends ClipCard {
  skills: string[]        // 页面上的技能标签 → 直接当 keywords
  description: string     // 职位描述全文
  responsibilities: string[]; requirements: string[]   // 规则拆分结果，失败时为空
}
```

**BOSS 适配器的选择器单独放成配置**（`boss.selectors.ts`），每个字段配多个候选选择器，按顺序尝试。BOSS 改版时只需要改这一个文件：

```ts
export const BOSS = {
  card: ['.job-card-wrapper', '.job-card-box', 'li.job-card'],      // 候选值，需要用真实 HTML 核对
  cardTitle: ['.job-name', '.job-title'],
  cardSalary: ['.salary', '.job-salary'],
  cardTags: ['.tag-list li', '.job-info .tag'],
  cardCompany: ['.company-name', '.boss-name'],
  cardArea: ['.job-area', '.company-location'],
  detailRoot: ['.job-detail-box', '.job-detail-container', '.job-detail'],
  detailSkills: ['.job-label-list li', '.job-keyword-list li'],
  detailDesc: ['.job-sec-text', '.desc'],
}
```

> ⚠️ 这些类名是凭经验写的候选值。**实施前需要你提供真实页面的 HTML 样本**（见 §9），我会按样本核对，并把样本做成测试用例。

**兜底策略（选择器全部失效时）：**

1. 用户选中了文字 → 只用选中内容，交给“粘贴 JD”那套解析流程；
2. 启发式识别：找出“同时含有薪资格式（如 `\d+-\d+(K|元/天)`）和链接”的重复兄弟元素，当作卡片列表；
3. 最后用页面纯文本，交给大模型抽取（也就是现在的做法）。

**职责 / 要求的规则拆分：**

- 按“职位描述 / 岗位职责 / 工作内容”和“职位要求 / 任职要求 / 任职资格”这些小标题切成两段；
- 每段里按 `1、` `2.` `•` 这类编号切成条目；
- 两段都没切出来时，才调用一次 fast 模型。

### 3.3 /clip 小窗口的交互

```text
┌ 收藏到 CareerCraft ─────────────────────────── 来源：BOSS直聘 ┐
│ ■ 当前职位（完整 JD）                                         │
│   大模型Agent业务开发实习生-剪映   500-550元/天               │
│   字节跳动 · 深圳·南山区 · 4天/周 · 4个月 · 本科              │
│   技能：agent  api调用  Langchain  大模型  Python             │
│   [展开查看职责/要求]                [保存到职位库]           │
│───────────────────────────────────────────────────────────────│
│ □ 本页列表中的职位（20）   [全选] [只选符合偏好的]            │
│   ☑ 测试实习生（AI Agent…）   200-250元/天  视界之外  ✓符合   │
│   ☐ Agent产品经理实习生       270-320元/天  百度      ✗不符   │
│   …                                                           │
│   [加入线索]   [加入职位库（摘要，之后可补全详情）]            │
└───────────────────────────────────────────────────────────────┘
```

- 每张卡片当场用求职偏好判断“符合 / 不符”（规则计算，不调用大模型）；
- 和职位库或线索中已有的链接重复时，显示“已收藏”，不会重复保存；
- 收藏的详情页链接如果命中某条线索，这条线索自动标记为“已转入职位库”。

### 3.4 安全与合规

- 只接受白名单招聘网站发来的消息（沿用现有的 `isAllowedClipOrigin`）；
- 页面内容只用 `DOMParser` 解析、只读取文本，绝不插入到 CareerCraft 页面里执行；
- 书签读不到、也不会发送 BOSS 的 cookie 或登录信息；
- 不自动翻页、不自动点击，只处理用户当前看到的这一页；
- 报告里的表述：“用户主动触发的单页收藏工具，作用相当于复制粘贴”。

---

## 4. 发现线索（搜索改为零大模型）

### 4.1 搜索来源

求职偏好里新增“线索来源”多选，默认全选：

| 来源 | 域名 | 说明 |
|---|---|---|
| BOSS 直聘 | zhipin.com | 收录少，但保留 |
| 腾讯校招 | join.qq.com | 校招官网，通常不用登录，搜索引擎收录相对好 |
| 字节跳动校招 | jobs.bytedance.com | 同上 |
| 阿里巴巴校招 | talent.alibaba.com | 同上 |
| 华为校招 | career.huawei.com | 同上 |
| 牛客 / 实习僧 | nowcoder.com / shixiseng.com | 实习类较多 |

### 4.2 规则过滤（顺序执行，全部不调用大模型）

1. **域名白名单**：只保留上表里勾选的来源；
2. **必须是详情页**：每个站点配一条链接规则（如 BOSS 只认 `/job_detail/`），列表页、公司页、资讯页一律丢掉；
3. **失效关键词**：标题或摘要里出现“暂停招聘 / 已下线 / 停止招聘 / 职位已关闭 / 已结束”的丢掉；
4. **城市硬过滤**：设置了期望城市时，标题或摘要里出现了其它城市名、却没有出现期望城市的丢掉；一个城市都没提到的保留，标注“城市未知”；
5. **职位名称相关度**：和目标职位的二元组重合度低于 0.4 的丢掉；
6. **收录时间**：搜索结果给的日期统一显示为“收录于 11月12日”，超出 `JOB_FRESH_DAYS` 的丢掉；
7. **去重**：和已有线索、职位库的链接比对，已经存在的不再加入。

### 4.3 线索打分（纯规则）

```text
lead_score = 职位名称相关度 × 50
           + 摘要中命中“我的技能”的比例 × 30
           + 城市（符合 1 / 未知 0.5）× 10
           + 新鲜度（收录 ≤7 天 1 / ≤30 天 0.5 / 其它 0）× 10
```

### 4.4 “去 BOSS 搜索”深链接（零成本、最准）

在线索页放一个按钮：按求职偏好直接拼出 BOSS 的搜索链接，在新标签页打开，用户在 BOSS 上筛选、浏览，再用书签收藏。

```text
https://www.zhipin.com/web/geek/job?query=<职位>&city=<城市代码>
```

城市代码先内置常用城市（深圳 101280600、北京 101010100、上海 101020100、广州 101280100、杭州 101210100 等），**实施时需要逐个打开验证**。这个按钮只是帮用户打开网页，不涉及任何抓取。

---

## 5. 今日推荐的重新定义

`GET /api/today` 实时计算，不再把“推送”写成职位的一个属性：

| 区块 | 内容 | 来源 |
|---|---|---|
| 新线索 | 按求职偏好每日自动搜索得到的新线索，按 lead_score 取前 N 条 | 定时任务（只搜索，不调用大模型） |
| 待处理提醒 | 收藏超过 3 天还没投递的职位、投递超过 14 天还没有进展的职位 | 职位库 |
| 投递漏斗 | 已收藏 / 已投递 / 笔试 / 面试 / offer 各有多少个 | 职位库 |

定时任务继续沿用现在的 `push_tick`（每天按设定时间、每人一次），只是改成生成线索。

---

## 6. 数据模型变更

### 6.1 Job（职位库）新增列

| 列 | 类型 | 说明 |
|---|---|---|
| `site` | str | boss / liepin / campus / paste … |
| `origin` | str | clip_detail / clip_card / paste / lead |
| `detail_level` | str | full / summary（摘要级的职位不能生成简历，界面提示去补全） |
| `status` | str | saved / applied / written_test / interview / offer / rejected / dropped |
| `status_history` | JSON | `[{status, at, note}]`，用来画时间线 |
| `notes` | Text | 用户备注 |
| `updated_at` | datetime | |

`pushed_date` 保留在表里但不再使用（SQLite 删列麻烦，留着无害）。

### 6.2 新表 Lead（线索）

| 列 | 说明 |
|---|---|
| id, user_id | |
| url（同一用户下唯一）, site | 规范化后的链接 |
| title, snippet, salary, city_guess | 规则提取 |
| date_text | 收录时间原文 |
| query | 由哪个搜索词找到的 |
| score | lead_score |
| status | new / dismissed / converted |
| job_id | 转入职位库后关联的职位 |
| found_date, created_at | found_date 用于“今日新线索” |

### 6.3 迁移

- 继续使用 `db.py` 里的 `_ADDED_COLUMNS` 给 Job 补列，新表由 `create_all` 自动创建；
- 一次性数据迁移：现有 Job 中由搜索产生的（链接不为空、且不是用户导入的），**转成线索**；粘贴导入的职位保留在职位库，status 设为 saved。迁移脚本放在 `scripts/migrate_plan_c.py`，执行前先备份数据库文件。

---

## 7. 接口变更

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/clip/save | body `{detail?, cards[], target: "jobs"\|"leads"}`；解析已经在前端完成，后端做校验、去重、打分；职责/要求为空时才调用大模型补全 |
| GET | /api/jobs?status= | 职位库，按投递状态筛选 |
| PATCH | /api/jobs/{id} | 修改 status / notes（自动追加一条 status_history） |
| GET | /api/leads?status=new | 线索列表 |
| POST | /api/leads/search | 手动按偏好搜一次（只搜索和规则过滤） |
| POST | /api/leads/{id}/dismiss | 忽略 |
| POST | /api/leads/{id}/convert | 按摘要转入职位库（detail_level=summary） |
| GET | /api/today | 新线索 + 提醒 + 漏斗 |
| GET | /api/boss-link | 按偏好生成 BOSS 搜索深链接 |
| 删除 | POST /api/jobs/search | 被 /api/leads/search 替代 |
| 保留 | POST /api/jobs/import | 粘贴 JD，进入职位库 |

---

## 8. 代码改动清单

```text
agents/jd_agent/
  lead_filter.py        新增：域名白名单 / 详情页链接规则 / 失效词 / 城市硬过滤 / 相关度 / 去重 / lead_score
  jd_split.py           新增：职责与要求的规则拆分（大模型只作兜底）
  sites.py              新增：各来源的域名、详情页链接规则、BOSS 城市代码表
  agent.py              修改：search_jobs → discover_leads（不再调用大模型）；normalize_text 保留给粘贴 JD
backend/app/
  models.py             修改：Job 新增列，新增 Lead
  db.py                 修改：_ADDED_COLUMNS 增加 Job 的新列
  routers/clip.py       新增：/api/clip/save
  routers/leads.py      新增
  routers/jobs.py       修改：status / notes、PATCH；删除 /jobs/search
  services/jobs.py      修改：push_for_user → discover_for_user（生成线索）、today 汇总
scripts/migrate_plan_c.py  新增
frontend/src/
  utils/bookmarklet.ts  修改：v2 搬运脚本（发送清理后的 HTML）
  clip/adapters/        新增：boss.ts / boss.selectors.ts / liepin.ts / generic.ts / index.ts
  clip/split.ts         新增：前端版职责/要求拆分（预览用）
  views/ClipView.vue    重写：当前详情 + 列表多选
  views/JobsView.vue    重写为三个分区：职位库 | 发现线索 | 今日推荐
  components/jobs/StatusSteps.vue, LeadRow.vue, Funnel.vue  新增
  views/HomeView.vue    修改：今日推荐改为 线索 + 提醒 + 漏斗
tests/
  fixtures/clip/boss_search.html, boss_detail.html …   ← 来自你提供的真实页面
  test_lead_filter.py, test_jd_split.py, test_clip_save.py
  frontend：adapters 用 vitest + 同一批样本 HTML 测试（新增 vitest 依赖）
```

---

## 9. 分阶段执行计划

| 阶段 | 内容 | 验收标准 | 估时 |
|---|---|---|---|
| **P0 采集样本**（需要你） | 用浏览器“另存为 → 网页，仅 HTML”保存：① 截图这种 BOSS 搜索页（选中某个职位、右侧显示详情的状态）② 一个 BOSS 职位详情页 ③（可选）猎聘或实习僧的详情页。放到 `tests/fixtures/clip/` | 文件里能找到职位卡片和职位描述的文字 | 10 分钟 |
| P1 数据模型与迁移 | Job 新增列、Lead 表、迁移脚本 | 旧数据库启动不报错；搜索产生的旧职位转成了线索 | 0.5 天 |
| P2 书签 v2 + BOSS 适配器 | 搬运脚本、适配器、规则拆分、/clip 新界面、/api/clip/save | 用 P0 样本做测试：卡片数量、标题、薪资、公司、技能标签全部正确；详情的职责/要求不调用大模型就能拆开 | 1.5 天 |
| P3 职位库 | 投递状态、备注、时间线；摘要级职位提示“去补全详情” | 能把一个职位从“已收藏”一路推进到 offer，时间线正确 | 1 天 |
| P4 发现线索 | lead_filter、来源配置、零大模型搜索、线索页、BOSS 深链接 | 线索里不出现其它城市（城市未知的除外）、失效页和列表页；一次搜索不调用任何大模型 | 1 天 |
| P5 今日推荐与首页 | /api/today、定时任务改为生成线索、首页漏斗 | 点“立即推送一次”后首页出现新线索和提醒 | 0.5 天 |
| P6 测试与演示 | 单元测试、样本测试、演示数据、README 和报告素材 | `pytest` 与 `vitest` 全部通过；演示脚本走通 | 0.5 天 |

合计约 5 人日。三个人并行（后端 P1/P4/P5、前端 P2/P3、测试与文档 P6）大约 2～3 天。

**依赖关系**：P0 → P2；P1 → P3、P4 → P5。P2 和 P1 可以同时开工。

---

## 10. 演示脚本（新版）

1. 设置求职偏好：Agent 开发实习 / 深圳 / 150-600 元/天；
2. 线索页点“去 BOSS 搜索”→ 打开 BOSS（就是截图里的页面）；
3. 点一次书签 → 小窗口显示当前职位的完整 JD，加上左侧 20 个职位卡片和“符合 / 不符”标记 → 当前职位“保存到职位库”，再勾选 5 个“加入线索”；
4. 职位库：刚收藏的职位技能标签齐全（agent / Langchain / Python…），匹配分和缺失技能一目了然 → 生成定向简历 → 状态改为“已投递”；
5. 线索页：点一条线索的“打开原文”→ 在详情页点书签补全 → 线索自动转入职位库；
6. 首页：今日新线索、“2 个职位收藏超过 3 天未投递”提醒、投递漏斗；
7. 讲合规：机器只负责找线索，进入 AI 流程的每个职位都由用户确认。

---

## 11. 风险与对策

| 风险 | 对策 |
|---|---|
| BOSS 改版导致选择器失效 | 选择器集中在一个配置文件，每个字段多个候选；还有启发式识别和纯文本兜底两层；书签本身不用改 |
| 我没法直接访问 BOSS 页面 | 用 P0 的 HTML 样本开发和测试；样本同时作为回归测试的固定数据 |
| 页面体积太大 | 书签删掉脚本、样式和图片，并限制 1.5 MB；超限时只发送主体区域 |
| 浏览器拦截弹窗 | 小窗口给出提示；也可以改成在当前页面里放一个悬浮条（v2 之后再考虑） |
| 线索仍然不准 | 线索只是参考，不会进入 AI 流程；“去 BOSS 搜索”深链接才是主路径 |
| 迁移时丢数据 | 迁移脚本执行前自动把数据库复制一份 `careercraft.db.bak` |

---

## 12. 需要你确认的事项

1. 线索来源默认勾选哪些？建议：BOSS + 四家大厂校招官网 + 实习僧。
2. 投递状态这几档是否合适：已收藏 / 已投递 / 笔试 / 面试 / offer / 未通过 / 已放弃？
3. 求职偏好要不要加实习专属的条件，比如“每周到岗天数 ≥ X”“实习时长”？BOSS 卡片上本来就有“4天/周 · 4个月”，加上很容易。
4. 发 P0 的 HTML 样本给我（另存为 → 仅 HTML 即可，文件里可能有你的用户名，保存后可以手动把它替换掉）。
