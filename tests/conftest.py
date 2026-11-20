"""Every test gets a fresh harness runtime: scripted LLM + in-memory memory store (no network, no key)."""

import pytest

from agents.harness import configure, reset_runtime
from agents.harness.llm import ScriptedProvider
from agents.harness.memory import SQLiteMemoryStore


@pytest.fixture(autouse=True)
def llm():
    provider = ScriptedProvider()
    configure(provider=provider, store=SQLiteMemoryStore(":memory:"))
    yield provider
    reset_runtime()
