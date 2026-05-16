"""Tests for orchestrator JSON parsing logic (no API required)."""

import pytest
from src.core.orchestrator import Orchestrator


class MockAgent:
    total_tokens_used = 0
    async def run(self, _): return ""
    def format_input(self, task): return str(task)


@pytest.fixture
def orchestrator():
    return Orchestrator(
        planner=MockAgent(),
        coder=MockAgent(),
        reviewer=MockAgent(),
        config={"max_review_rounds": 3, "review_threshold": 7.0},
    )


def test_parse_plan_json(orchestrator):
    text = '```json\n{"tasks": [{"task_id": "T1", "description": "Do X", "dependencies": []}]}\n```'
    tasks = orchestrator._parse_plan(text)
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == "T1"


def test_parse_plan_numbered_list(orchestrator):
    text = "1. Create the class\n2. Add methods\n3. Write tests"
    tasks = orchestrator._parse_plan(text)
    assert len(tasks) == 3
    assert "Create the class" in tasks[0]["description"]


def test_parse_plan_fallback(orchestrator):
    text = "Just do everything in one go"
    tasks = orchestrator._parse_plan(text)
    assert len(tasks) == 1


def test_parse_review_json(orchestrator):
    text = '{"score": 8.5, "passed": true, "issues": ["minor"], "suggestions": [], "summary": "Good"}'
    review = orchestrator._parse_review(text)
    assert review["score"] == 8.5
    assert review["passed"] is True


def test_parse_review_fallback(orchestrator):
    text = "The code scores 6.5 / 10. Needs improvement."
    review = orchestrator._parse_review(text)
    assert review["score"] == 6.5
    assert review["passed"] is False
