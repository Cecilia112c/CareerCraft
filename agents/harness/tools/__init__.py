from agents.harness.tools.base import Tool, ToolContext, ToolResult
from agents.harness.tools.builtin import BUILTIN_TOOLS
from agents.harness.tools.executor import ToolExecutor, observation_text
from agents.harness.tools.policy import Decision, ToolPolicy
from agents.harness.tools.registry import ToolRegistry


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool_cls in BUILTIN_TOOLS:
        registry.register(tool_cls())
    return registry


__all__ = ["Tool", "ToolContext", "ToolResult", "ToolExecutor", "observation_text", "Decision",
           "ToolPolicy", "ToolRegistry", "default_registry", "BUILTIN_TOOLS"]
