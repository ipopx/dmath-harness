"""Tests for the agent exam JSONL runner."""

import json
from pathlib import Path

from dmath_harness.agent_run import run_agent_exam
from dmath_harness.client import ChatClient, ChatConfig, ChatResult, Usage
from dmath_harness.exam import load_exam


ROOT = Path(__file__).resolve().parents[1]
MOCK_EXAM = ROOT / "data" / "exams" / "dmath-mock-2024-hs.json"


class FakeClient(ChatClient):
    def __init__(self) -> None:
        self.config = ChatConfig(
            base_url="http://test.local/v1",
            api_key="test",
            model="fake-model",
        )

    def chat(self, messages, *, tools=None):  # type: ignore[override]
        text = "Final answer: A"
        return ChatResult(
            text=text,
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            latency_ms=1.5,
            raw_finish_reason="stop",
            tool_calls=[],
            assistant_message={"role": "assistant", "content": text},
        )


def test_run_agent_exam_writes_jsonl(tmp_path: Path):
    exam = load_exam(MOCK_EXAM)
    out = tmp_path / "agent_traj.jsonl"
    run_agent_exam(exam, FakeClient(), out, question_ids=["Q1"], step_limit=4)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["question_id"] == "Q1"
    assert record["harness"] == "react"
    assert record["finished"] is True
    assert record["step_count"] == 1
    assert record["step_limit"] == 4
    assert record["assistant_text"] == "Final answer: A"
    assert "steps" in record
    assert record["model"] == "fake-model"
