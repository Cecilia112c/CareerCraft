"""CareerCraft agent harness.

    harness/
      spec.py           AgentSpec / MemoryPolicy / Budget   —— 每个 agent 任务的静态策略
      request.py        InvocationRequest / ExecutionContext / InvocationResult
      runtime.py        AgentRuntime.invoke()                —— 唯一的模型执行入口
      llm/              模型提供方（OpenAI 兼容、测试用 Scripted）
      context/          上下文槽位编译、token 预算、提示模板
      memory/           长期记忆（偏好）、工作记忆（摘要 + 最近轮次）、情景记录、SQLite 存储
      tools/            工具基类、注册表、鉴权策略（白名单/权限范围/频率/归属/写入确认）、执行器、内置工具
      validation/       输出校验流水线（语法 → 结构 → 领域）
      skills/           SKILL.md 目录与加载
      observability/    AgentRun 运行记录
"""

from agents.harness.errors import AgentError, BudgetExhausted, ContextBudgetExceeded, ProviderError, ValidationFailed
from agents.harness.request import ExecutionContext, InvocationRequest, InvocationResult, Report, noop_report
from agents.harness.runtime import AgentRuntime, configure, get_runtime, invoke, reset_runtime
from agents.harness.spec import AgentSpec, Budget, ContextContract, MemoryPolicy

__all__ = ["AgentError", "BudgetExhausted", "ContextBudgetExceeded", "ProviderError", "ValidationFailed",
           "ExecutionContext", "InvocationRequest", "InvocationResult", "Report", "noop_report",
           "AgentRuntime", "configure", "get_runtime", "invoke", "reset_runtime",
           "AgentSpec", "Budget", "ContextContract", "MemoryPolicy"]
