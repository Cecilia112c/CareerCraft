"""Central tool registry. Registration rejects unsafe definitions up front."""

from __future__ import annotations

import re

from agents.harness.errors import ConfigError
from agents.harness.tools.base import Tool

FORBIDDEN_ARGS = {"user_id", "owner", "owner_id", "tenant_id", "uid"}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        name = getattr(tool, "name", "")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", name or ""):
            raise ConfigError(f"invalid tool name: {name!r}")
        if name in self._tools:
            raise ConfigError(f"tool already registered: {name}")
        if tool.args_model.model_config.get("extra") != "forbid":
            raise ConfigError(f"{name}: args_model must set extra='forbid'")
        bad = FORBIDDEN_ARGS & set(tool.args_model.model_fields)
        if bad:
            raise ConfigError(f"{name}: tools must not accept owner arguments {sorted(bad)}")
        self._tools[name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
