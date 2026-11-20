"""Compatibility layer. All model calls now go through agents.harness (AgentRuntime.invoke).

Kept: Report / noop_report / parallel_map / AgentError / extract_json, used across the agents.
run_json() remains for old callers; new code should define an AgentSpec and call harness.invoke().
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from pathlib import Path
from typing import Callable, Iterable, TypeVar

from pydantic import BaseModel

from agents.harness import AgentError, AgentSpec, Budget, invoke
from agents.harness.request import Report, noop_report
from agents.harness.validation import extract_json

T = TypeVar("T", bound=BaseModel)

__all__ = ["Report", "noop_report", "parallel_map", "AgentError", "extract_json", "run_json"]


def run_json(prompt_path: Path, variables: dict, out: type[T], *, tier: str = "fast",
             user_text: str = "", temperature: float = 0.3) -> T:
    spec = AgentSpec(id="legacy.run_json", agent="legacy", prompt=prompt_path, output=out, tier=tier,
                     budget=Budget(temperature=temperature))
    return invoke(spec, variables=variables, instruction=user_text).output


def parallel_map(fn: Callable, items: Iterable, workers: int = 4) -> list:
    items = list(items)
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as pool:
        futures = [pool.submit(copy_context().run, fn, item) for item in items]
        return [future.result() for future in futures]
