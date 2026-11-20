"""Skill-demand insight (no LLM): which skills appear in how many JDs, and which of them I have.

Two sources, same aggregation:
  library  我收藏的职位（准确，JD 完整）
  market   搜索引擎里目标岗位的 JD 摘要样本（只统计词频，不展示职位——岗位过期不影响结论）

Counting is document frequency (一个词在一份 JD 里出现多次只算一次)，并做同义词归一（golang→Go，k8s→Kubernetes…）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# canonical: (category, aliases...)   短英文别名（≤3 个字符）区分大小写，避免误匹配
LEXICON: dict[str, tuple[str, ...]] = {
    # 编程语言
    "Python": ("lang", "python"), "Java": ("lang", "java"), "Go": ("lang", "Go", "golang"),
    "C++": ("lang", "c++", "cpp"), "C#": ("lang", "c#"), "C语言": ("lang", "C语言"),
    "JavaScript": ("lang", "javascript", "JS"), "TypeScript": ("lang", "typescript", "TS"),
    "Rust": ("lang", "rust"), "Kotlin": ("lang", "kotlin"), "Swift": ("lang", "swift"),
    "PHP": ("lang", "php"), "Scala": ("lang", "scala"), "Shell": ("lang", "shell", "bash"),
    "SQL": ("lang", "sql"), "MATLAB": ("lang", "matlab"),
    # 前端 / 客户端
    "Vue": ("fe", "vue", "vue.js", "vue3"), "React": ("fe", "react", "react.js"), "HTML/CSS": ("fe", "html", "css"),
    "Node.js": ("fe", "node.js", "nodejs", "node"), "小程序": ("fe", "小程序"), "Webpack": ("fe", "webpack", "vite"),
    "Android": ("fe", "android", "安卓"), "iOS": ("fe", "iOS"), "Flutter": ("fe", "flutter"),
    # 后端框架 / 架构
    "Spring": ("be", "spring", "springboot", "spring boot", "spring cloud"), "Django": ("be", "django"),
    "Flask": ("be", "flask"), "FastAPI": ("be", "fastapi"), "Gin": ("be", "gin"),
    "微服务": ("be", "微服务", "microservice"), "分布式": ("be", "分布式", "distributed"),
    "高并发": ("be", "高并发", "高可用"), "RPC": ("be", "rpc", "grpc", "thrift", "dubbo"),
    "RESTful API": ("be", "restful", "rest api", "api设计", "api 设计"), "设计模式": ("be", "设计模式"),
    "数据结构与算法": ("be", "数据结构", "算法基础", "leetcode"), "操作系统": ("be", "操作系统"),
    "计算机网络": ("be", "计算机网络", "tcp/ip", "http协议"), "多线程": ("be", "多线程", "并发编程"),
    # 数据存储 / 中间件
    "MySQL": ("data", "mysql"), "PostgreSQL": ("data", "postgresql", "postgres"), "Redis": ("data", "redis"),
    "MongoDB": ("data", "mongodb", "mongo"), "Elasticsearch": ("data", "elasticsearch", "ES"),
    "Kafka": ("data", "kafka"), "RabbitMQ": ("data", "rabbitmq"), "消息队列": ("data", "消息队列", "MQ"),
    "ClickHouse": ("data", "clickhouse"), "HBase": ("data", "hbase"), "Hive": ("data", "hive"),
    "Spark": ("data", "spark", "pyspark"), "Flink": ("data", "flink"), "Hadoop": ("data", "hadoop"),
    "数据仓库": ("data", "数据仓库", "数仓"), "ETL": ("data", "etl"),
    # 云 / 运维
    "Linux": ("ops", "linux"), "Docker": ("ops", "docker", "容器"), "Kubernetes": ("ops", "kubernetes", "k8s"),
    "Git": ("ops", "git", "github", "gitlab"), "CI/CD": ("ops", "ci/cd", "jenkins", "持续集成"),
    "云计算": ("ops", "云计算", "aws", "阿里云", "腾讯云"), "Nginx": ("ops", "nginx"),
    # AI / 算法
    "机器学习": ("ai", "机器学习", "machine learning"), "深度学习": ("ai", "深度学习", "deep learning"),
    "PyTorch": ("ai", "pytorch", "torch"), "TensorFlow": ("ai", "tensorflow"),
    "大模型": ("ai", "大模型", "LLM", "大语言模型", "gpt"), "Agent": ("ai", "agent", "智能体"),
    "LangChain": ("ai", "langchain", "llamaindex"), "RAG": ("ai", "RAG", "检索增强"),
    "Prompt": ("ai", "prompt", "提示词"), "微调": ("ai", "微调", "fine-tune", "fine-tuning", "lora", "sft"),
    "NLP": ("ai", "nlp", "自然语言处理"), "计算机视觉": ("ai", "计算机视觉", "CV", "图像识别", "opencv"),
    "推荐系统": ("ai", "推荐系统", "推荐算法"), "搜索算法": ("ai", "搜索算法", "搜索引擎"),
    "强化学习": ("ai", "强化学习"), "多模态": ("ai", "多模态"), "向量数据库": ("ai", "向量数据库", "milvus", "faiss"),
    # 数据分析 / 产品
    "数据分析": ("biz", "数据分析"), "Excel": ("biz", "excel"), "Tableau": ("biz", "tableau", "power bi", "powerbi"),
    "A/B 测试": ("biz", "a/b", "ab测试", "ab 测试"), "统计学": ("biz", "统计学", "统计分析"),
    "Pandas": ("biz", "pandas", "numpy"), "用户研究": ("biz", "用户研究", "用户调研"),
    "需求分析": ("biz", "需求分析", "prd", "需求文档"), "Axure/Figma": ("biz", "axure", "figma", "原型设计"),
    "项目管理": ("biz", "项目管理", "敏捷", "scrum"),
    # 测试
    "自动化测试": ("qa", "自动化测试", "selenium", "pytest", "接口测试"), "性能测试": ("qa", "性能测试", "压测", "jmeter"),
    # 通用素质（单独归类，前端可选择隐藏）
    "沟通能力": ("soft", "沟通能力", "沟通协调", "表达能力"), "团队协作": ("soft", "团队协作", "团队合作"),
    "英语": ("soft", "英语", "英文", "cet-6", "cet6"), "学习能力": ("soft", "学习能力"),
}
CATEGORY_LABELS = {"lang": "编程语言", "fe": "前端/客户端", "be": "后端/架构", "data": "数据/中间件",
                   "ops": "运维/云", "ai": "AI/算法", "biz": "数据分析/产品", "qa": "测试", "soft": "通用素质"}

_ALIAS: list[tuple[re.Pattern, str]] = []
for canonical, (category, *aliases) in LEXICON.items():
    for alias in {canonical, *aliases}:
        if re.search(r"[一-鿿]", alias):
            pattern = re.compile(re.escape(alias))
        elif len(alias) <= 3 and alias.isalpha():
            pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])")      # 区分大小写
        else:
            pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9+#])", re.I)
        _ALIAS.append((pattern, canonical))
_CANON_LOWER = {k.lower(): k for k in LEXICON}
_ALIAS_LOWER = {a.lower(): k for k, (_, *aliases) in LEXICON.items() for a in aliases}


def canonical(term: str) -> str | None:
    t = (term or "").strip()
    if not t:
        return None
    return _CANON_LOWER.get(t.lower()) or _ALIAS_LOWER.get(t.lower())


def extract_terms(text: str, extra_keywords: list[str] | None = None) -> set[str]:
    found = {canon for pattern, canon in _ALIAS if pattern.search(text or "")}
    for kw in extra_keywords or []:           # 大模型从 JD 里提取的关键词：能归一就归一，否则保留原词
        c = canonical(kw)
        if c:
            found.add(c)
        elif 2 <= len(kw.strip()) <= 12 and not re.search(r"[，。,.;；:：]", kw):
            found.add(kw.strip())
    return found


@dataclass
class TermStat:
    term: str
    count: int
    ratio: float
    have: bool
    category: str
    doc_ids: list = field(default_factory=list)


@dataclass
class Insight:
    total_docs: int
    terms: list[TermStat]
    coverage: float            # 前 15 个热门技能中，我具备的占比（按出现次数加权）
    missing_top: list[str]
    have_top: list[str]

    def as_dict(self) -> dict:
        return {"total_docs": self.total_docs, "coverage": self.coverage, "missing_top": self.missing_top,
                "have_top": self.have_top,
                "terms": [{"term": t.term, "count": t.count, "ratio": t.ratio, "have": t.have,
                           "category": t.category, "category_label": CATEGORY_LABELS.get(t.category, "其他"),
                           "doc_ids": t.doc_ids[:500]} for t in self.terms],
                "categories": CATEGORY_LABELS}


def aggregate(docs: list[tuple[object, set[str]]], my_terms: set[str], top: int = 40,
              include_soft: bool = True) -> Insight:
    counts: dict[str, list] = {}
    for doc_id, terms in docs:
        for t in terms:
            counts.setdefault(t, []).append(doc_id)
    stats = []
    total = max(len(docs), 1)
    my_lower = {m.lower() for m in my_terms}
    for term, ids in counts.items():
        category = LEXICON.get(term, ("other",))[0]
        if category == "soft" and not include_soft:
            continue
        stats.append(TermStat(term=term, count=len(ids), ratio=round(len(ids) / total, 3),
                              have=term.lower() in my_lower, category=category, doc_ids=ids))
    stats.sort(key=lambda s: (-s.count, s.category == "soft", s.term))
    stats = stats[:top]
    hard = [s for s in stats if s.category != "soft"][:15]
    weight = sum(s.count for s in hard)
    coverage = round(sum(s.count for s in hard if s.have) / weight, 2) if weight else 0.0
    return Insight(total_docs=len(docs), terms=stats, coverage=coverage,
                   missing_top=[s.term for s in hard if not s.have][:8],
                   have_top=[s.term for s in hard if s.have][:8])


def job_text(data: dict) -> str:
    parts = [data.get("title", ""), data.get("summary", ""), " ".join(data.get("requirements") or []),
             " ".join(data.get("responsibilities") or [])]
    return "\n".join(p for p in parts if p)
