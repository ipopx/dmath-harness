"""Tests for the ReAct Agent loop."""

from __future__ import annotations

from typing import Any

from dmath_harness.agent import Agent
from dmath_harness.client import ChatClient, ChatConfig, ChatResult, ToolCall, Usage
from dmath_harness.exam import Question


def _question() -> Question:
    return Question(
        id="Q2",
        type="short_answer",
        topic="combinatorics",
        difficulty="medium",
        points=6.0,
        prompt="How many ways to choose 3 from 10?",
    )


class ScriptedClient(ChatClient):
    """Returns a scripted sequence of ChatResults; ignores the real API."""

    def __init__(self, script: list[ChatResult]) -> None:
        self.config = ChatConfig(
            base_url="http://test.local/v1",
            api_key="test",
            model="fake-model",
        )
        self._script = list(script)
        self._i = 0
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages, *, tools=None):  # type: ignore[override]
        self.calls.append({"messages": list(messages), "tools": tools})
        if self._i >= len(self._script):
            raise AssertionError("ScriptedClient exhausted")
        result = self._script[self._i]
        self._i += 1
        return result


def _tool_result(expression: str = "(10*9*8)/(3*2*1)") -> ChatResult:
    tc = ToolCall(
        id="call_1",
        name="calculator",
        arguments=f'{{"expression": "{expression}"}}',
    )
    return ChatResult(
        text="",
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        latency_ms=1.0,
        raw_finish_reason="tool_calls",
        tool_calls=[tc],
        assistant_message={
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "arguments": tc.arguments,
                    },
                }
            ],
        },
    )


def _final_result(text: str = "Final answer: 120") -> ChatResult:
    return ChatResult(
        text=text,
        usage=Usage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
        latency_ms=2.0,
        raw_finish_reason="stop",
        tool_calls=[],
        assistant_message={"role": "assistant", "content": text},
    )


def test_agent_tool_then_finish():
    client = ScriptedClient([_tool_result(), _final_result()])
    agent = Agent(client, step_limit=8)
    result = agent.run(_question())

    assert result.finished is True
    assert agent.finished is True
    assert result.step_count == 2
    assert result.assistant_text == "Final answer: 120"
    assert result.usage.total_tokens == 45

    roles = [m["role"] for m in result.messages]
    assert roles[:2] == ["system", "user"]
    assert "assistant" in roles
    assert "tool" in roles

    tool_msgs = [m for m in result.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_1"
    assert tool_msgs[0]["content"] == "120"


def test_agent_step_limit_stops_unfinished():
    client = ScriptedClient([_tool_result("1+1"), _tool_result("2+2")])
    agent = Agent(client, step_limit=2)
    result = agent.run(_question())

    assert result.finished is False
    assert agent.finished is False
    assert result.step_count == 2
    assert len(client.calls) == 2


def test_agent_build_prompt():
    agent = Agent(ScriptedClient([]))
    messages = agent.build_prompt(_question())
    assert messages[0]["role"] == "system"
    assert "calculator" in messages[0]["content"].lower()
    assert "run_python" in messages[0]["content"].lower()
    assert messages[1]["role"] == "user"
    assert "choose 3 from 10" in messages[1]["content"]


def _run_python_tool_result(code: str = "print(42)") -> ChatResult:
    # Escape for JSON string inside arguments
    escaped = code.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    args = f'{{"code": "{escaped}"}}'
    tc = ToolCall(id="call_py", name="run_python", arguments=args)
    return ChatResult(
        text="",
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        latency_ms=1.0,
        raw_finish_reason="tool_calls",
        tool_calls=[tc],
        assistant_message={
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_py",
                    "type": "function",
                    "function": {"name": "run_python", "arguments": args},
                }
            ],
        },
    )


def test_agent_run_python_tool_then_finish(monkeypatch):
    from dmath_harness import agent as agent_mod

    def fake_dispatch(name: str, arguments_json: str) -> str:
        assert name == "run_python"
        assert "print(42)" in arguments_json
        return "42"

    monkeypatch.setattr(agent_mod, "dispatch_tool_call", fake_dispatch)

    client = ScriptedClient(
        [_run_python_tool_result(), _final_result("Final answer: 42")]
    )
    agent = Agent(client, step_limit=8)
    result = agent.run(_question())

    assert result.finished is True
    assert result.step_count == 2
    tool_msgs = [m for m in result.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_py"
    assert tool_msgs[0]["content"] == "42"
    assert result.assistant_text == "Final answer: 42"
