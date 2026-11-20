"""AgentRun: the auditable trace of one invocation (no sensitive body text, only refs/hashes/metrics)."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

log = logging.getLogger("careercraft.harness.runs")


@dataclass
class AgentRun:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    user_id: str = ""
    agent: str = ""
    spec_id: str = ""
    spec_version: str = ""
    session: str = ""
    workflow_step_id: str = ""
    status: str = "running"                # running / ok / failed
    model: str = ""
    tier: str = ""
    iterations: int = 0
    repairs: int = 0
    tool_calls: list[dict] = field(default_factory=list)
    visible_tools: list[str] = field(default_factory=list)
    skills: list[dict] = field(default_factory=list)
    memory: dict = field(default_factory=dict)          # 用了几条偏好、是否有工作记忆
    manifest: dict = field(default_factory=dict)
    usage: dict = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})
    error: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    duration_ms: int = 0
    _t0: float = field(default_factory=time.perf_counter, repr=False)

    def add_usage(self, usage: dict) -> None:
        for k in ("prompt_tokens", "completion_tokens"):
            self.usage[k] = self.usage.get(k, 0) + int(usage.get(k) or 0)

    def finish(self, status: str, error: str = "") -> dict:
        self.status, self.error = status, error[:500]
        self.duration_ms = round((time.perf_counter() - self._t0) * 1000)
        data = asdict(self)
        data.pop("_t0", None)
        return data


class RunRecorder:
    def __init__(self, store=None):
        self.store = store

    def record(self, run: dict) -> None:
        log.info("agent_run %s %s status=%s iter=%s tools=%s ms=%s", run["agent"], run["spec_id"], run["status"],
                 run["iterations"], len(run["tool_calls"]), run["duration_ms"])
        if self.store is not None:
            try:
                self.store.record_run(run)
            except Exception:  # noqa: BLE001  记录失败不影响业务
                log.exception("failed to record agent run")
