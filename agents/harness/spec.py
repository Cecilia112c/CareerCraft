"""AgentSpec: the static, versioned policy of one agent task (prompt, output, tools, memory, budget).

A spec never holds user data or state. Everything user-specific arrives through
InvocationRequest / ExecutionContext at call time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from pydantic import BaseModel

if TYPE_CHECKING:
    from agents.harness.request import InvocationRequest

Validator = Callable[[BaseModel, "InvocationRequest"], list[str]]
Summarizer = Callable[[BaseModel], str]

# 记忆命名空间：每个 agent 只能读写声明过的命名空间（面试 agent 只有 interview）
NAMESPACES = ("global", "resume", "jd", "interview", "parser", "knowledge")


@dataclass(frozen=True)
class MemoryPolicy:
    read_namespaces: tuple[str, ...] = ()     # 长期记忆（偏好）可读范围
    write_namespaces: tuple[str, ...] = ()    # 长期记忆可写范围（第一个为默认）
    use_working: bool = False                 # 是否把本会话的工作记忆（摘要 + 最近几轮）放进上下文
    record_working: bool = False              # 是否把本轮指令与结果写入工作记忆
    max_preferences: int = 12

    def __post_init__(self) -> None:
        bad = [n for n in (*self.read_namespaces, *self.write_namespaces) if n not in NAMESPACES]
        if bad:
            raise ValueError(f"unknown memory namespaces: {bad}")
        if not set(self.write_namespaces) <= set(self.read_namespaces):
            raise ValueError("write_namespaces must be a subset of read_namespaces")


@dataclass(frozen=True)
class Budget:
    max_input_tokens: int = 24000
    max_iterations: int = 4        # 模型调用次数上限（含工具轮与修复轮）
    max_tool_calls: int = 4        # 单次调用内工具调用总数上限
    max_repairs: int = 1           # 输出不合格时的修复次数
    temperature: float = 0.3


@dataclass(frozen=True)
class ContextContract:
    allowed_materials: tuple[str, ...] = ()
    allowed_variables: tuple[str, ...] | None = None
    forbidden: tuple[str, ...] = ()
    max_input_tokens: int | None = None


@dataclass(frozen=True)
class AgentSpec:
    id: str                                   # 例如 "resume.polish"
    agent: str                                # resume / jd / parser / interview
    prompt: Path                              # 系统提示模板（{{var}} 占位）
    output: type[BaseModel]                   # 输出契约
    description: str = ""
    tier: str = "fast"                        # fast / strong
    tools: tuple[str, ...] = ()               # 工具白名单（还要与请求白名单、权限范围求交集）
    skills: tuple[str, ...] = ()              # 预加载的 SKILL.md
    lazy_materials: tuple[str, ...] = ()      # 不预加载、需要时通过 get_material 工具获取的资料
    memory: MemoryPolicy = field(default_factory=MemoryPolicy)
    budget: Budget = field(default_factory=Budget)
    validators: tuple[Validator, ...] = ()    # 领域校验：返回问题列表，非空则进入修复
    summarize: Summarizer | None = None       # 写入工作记忆时如何概括输出
    version: str = "1"
    context_contract: ContextContract | None = None

    def __post_init__(self) -> None:
        if "." not in self.id or not self.id.startswith(self.agent + "."):
            raise ValueError(f"spec id must look like '<agent>.<task>': {self.id}")
        if self.lazy_materials and "get_material" not in self.tools:
            raise ValueError(f"{self.id}: lazy_materials require the get_material tool")
        if self.context_contract and self.context_contract.max_input_tokens and self.budget.max_input_tokens > self.context_contract.max_input_tokens:
            raise ValueError(f"{self.id}: budget exceeds context contract")
