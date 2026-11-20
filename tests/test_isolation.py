"""The interview agent must stay isolated from the other agents."""

import ast
from pathlib import Path

import pytest

from agents.interview_agent import IsolationError, validate_input

INTERVIEW_DIR = Path(__file__).resolve().parents[1] / "agents" / "interview_agent"
FORBIDDEN = ("agents.parser_agent", "agents.jd_agent", "agents.resume_agent")


def test_interview_agent_does_not_import_other_agents():
    for path in INTERVIEW_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert not name.startswith(FORBIDDEN), f"{path.name} imports {name}"


def _valid():
    return {"job": {"title": "后端开发实习生", "requirements": ["熟悉 Go"]},
            "resume_text": "张三 后端开发 实习经历：某公司 负责订单服务开发，使用 Go 和 Redis。",
            "history": []}


def test_valid_input_passes():
    assert validate_input(_valid()).job.title == "后端开发实习生"


def test_extra_top_level_field_is_rejected():
    raw = _valid() | {"evidence_ids": ["e1"]}
    with pytest.raises(IsolationError):
        validate_input(raw)


def test_extra_nested_field_is_rejected():
    raw = _valid()
    raw["job"]["match_score"] = 88          # jd_agent 的打分不能泄露给面试官
    with pytest.raises(Exception):
        validate_input(raw)
