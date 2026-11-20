"""Plan D workflow graphs. The coordinator executes these deterministic node names in order."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Node:
    name: str
    node_type: str


DEFINITIONS: dict[str, tuple[Node, ...]] = {
    "job_import": (Node("JD 已解析", "agent"),),
    "resume_generate": (Node("依据已匹配", "agent"), Node("等待补充资料", "gate"),
                        Node("定向简历已生成", "agent")),
    "knowledge_ingest": (Node("事实已抽取", "agent"), Node("等待事实确认", "gate")),
    "interview": (Node("面试视图已生成", "code"), Node("诊断与问题已生成", "agent"),
                  Node("等待面试回答", "gate"), Node("面试报告已生成", "agent"),
                  Node("补充建议已提出", "code")),
}
