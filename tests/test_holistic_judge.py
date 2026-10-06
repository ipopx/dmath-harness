"""Tests for tool-enabled holistic judge."""

from __future__ import annotations

from typing import Any

from dmath_harness.client import ChatClient, ChatConfig, ChatResult, ToolCall, Usage
from dmath_harness.judge.holistic import holistic_judge


class ScriptedJudgeClient(ChatClient):
    def __init__(self, script: list[ChatResult]) -> None:
        self.config = ChatConfig(
            base_url="http://test.local/v1",
            api_key="test",
            model="fake-judge",
        )
        self._script = list(script)
        self._i = 0
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages, *, tools=None):  # type: ignore[override]
        self.calls.append({"messages": list(messages), "tools": tools})
        assert tools is not None and len(tools) >= 2
        if self._i >= len(self._script):
            raise AssertionError("ScriptedJudgeClient exhausted")
        result = self._script[self._i]
        self._i += 1
        return result


def _calculator_step() -> ChatResult:
    tc = ToolCall(
        id="judge_call_1",
        name="calculator",
        arguments='{"expression": "1+1"}',
    )
    return ChatResult(
        text="",
        usage=Usage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
        latency_ms=1.0,
        raw_finish_reason="tool_calls",
        tool_calls=[tc],
        assistant_message={
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "judge_call_1",
                    "type": "function",
                    "function": {"name": "calculator", "arguments": tc.arguments},
                }
            ],
        },
    )


def _json_grade(points: float = 8.0, max_points: float = 10.0) -> ChatResult:
    text = (
        f'{{"points_awarded": {points}, "max_points": {max_points}, '
        f'"rationale": "solid work"}}'
    )
    return ChatResult(
        text=text,
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        latency_ms=1.0,
        raw_finish_reason="stop",
        tool_calls=[],
        assistant_message={"role": "assistant", "content": text},
    )


def test_holistic_judge_uses_agent_tools(monkeypatch):
    from dmath_harness import agent as agent_mod

    def fake_dispatch(name: str, arguments_json: str) -> str:
        assert name == "calculator"
        return "2"

    monkeypatch.setattr(agent_mod, "dispatch_tool_call", fake_dispatch)

    client = ScriptedJudgeClient([_calculator_step(), _json_grade(8.0)])
    award = holistic_judge(
        client,
        question_prompt="Prove something.",
        reference_answer="Ref proof.",
        key_ideas=["idea"],
        student_answer="Student proof.",
        max_points=10.0,
    )
    assert award.points_awarded == 8.0
    assert award.rationale == "solid work"
    assert not award.parse_error
    assert len(client.calls) == 2
    assert client.calls[0]["tools"] is not None


def test_holistic_judge_direct_json_no_tools():
    client = ScriptedJudgeClient([_json_grade(6.0, max_points=6.0)])
    award = holistic_judge(
        client,
        question_prompt="Method?",
        reference_answer="Use combinations.",
        key_ideas=None,
        student_answer="C(10,3).",
        max_points=6.0,
    )
    assert award.points_awarded == 6.0
    assert len(client.calls) == 1
