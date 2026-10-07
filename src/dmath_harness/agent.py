"""ReAct agent: message-list state, tool loop, step limit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dmath_harness.baseline import build_user_prompt
from dmath_harness.client import ChatClient, Usage
from dmath_harness.exam import Question
from dmath_harness.tools import TOOL_SCHEMAS, dispatch_tool_call
from dmath_harness.tools.run_python import begin_python_sandbox, end_python_sandbox

DEFAULT_STEP_LIMIT = 8

SYSTEM_PROMPT = """\
You are solving an ETH Zurich D-MATH (Department of Mathematics) exam question.
Answer in the same language as the question.
You may use tools:
- calculator: quick pure arithmetic expressions
- run_python: execute Python (stdlib, numpy, sympy); print results explicitly
When you are done, reply with your final solution and do not call tools.
Follow these output conventions:
- Multiple choice: state your reasoning briefly, then end with a single line \
`Final answer: X` where X is the choice letter (A, B, C, ...).
- Short answer / numeric: show a brief derivation, then end with \
`Final answer: <value>`.
- Proof: write a clear, structured proof. There is no separate final-answer line.
"""


@dataclass
class AgentRunResult:
    assistant_text: str
    messages: list[dict[str, Any]]
    usage: Usage
    steps: list[dict[str, Any]]
    finished: bool
    step_count: int


def _sum_usage(parts: list[Usage]) -> Usage:
    def _add(a: int | None, b: int | None) -> int | None:
        if a is None and b is None:
            return None
        return (a or 0) + (b or 0)

    prompt = completion = total = None
    for u in parts:
        prompt = _add(prompt, u.prompt_tokens)
        completion = _add(completion, u.completion_tokens)
        total = _add(total, u.total_tokens)
    return Usage(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)


class Agent:
    """ReAct loop over an OpenAI-compatible chat client with tools."""

    def __init__(
        self,
        client: ChatClient,
        *,
        step_limit: int = DEFAULT_STEP_LIMIT,
        system_prompt: str = SYSTEM_PROMPT,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        if step_limit < 1:
            raise ValueError("step_limit must be >= 1")
        self.client = client
        self.step_limit = step_limit
        self.system_prompt = system_prompt
        self.tools = tools if tools is not None else list(TOOL_SCHEMAS)
        self.messages: list[dict[str, Any]] = []
        self.finished = False
        self.steps: list[dict[str, Any]] = []

    def build_prompt(self, question: Question) -> list[dict[str, Any]]:
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": build_user_prompt(question)},
        ]

    def run(self, question: Question) -> AgentRunResult:
        return self.run_from_messages(self.build_prompt(question))

    def run_from_messages(self, messages: list[dict[str, Any]]) -> AgentRunResult:
        """ReAct loop from an initial message list (system/user/...)."""
        self.messages = list(messages)
        self.finished = False
        self.steps = []
        usages: list[Usage] = []
        last_text = ""

        # One Docker Python sandbox for this question; torn down when the run ends
        # (finished=True or step_limit exhausted).
        begin_python_sandbox()
        try:
            for step_idx in range(self.step_limit):
                result = self.client.chat(self.messages, tools=self.tools)
                usages.append(result.usage)
                assistant_msg = (
                    result.assistant_message
                    if result.assistant_message
                    else {"role": "assistant", "content": result.text}
                )
                self.messages.append(assistant_msg)
                self.steps.append(
                    {
                        "step": step_idx + 1,
                        "usage": result.usage.to_dict(),
                        "latency_ms": round(result.latency_ms, 2),
                        "finish_reason": result.raw_finish_reason,
                        "n_tool_calls": len(result.tool_calls),
                    }
                )

                if not result.tool_calls:
                    self.finished = True
                    last_text = result.text
                    break

                for tc in result.tool_calls:
                    observation = dispatch_tool_call(tc.name, tc.arguments)
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": observation,
                        }
                    )
                # Keep last assistant text if the model also wrote content alongside tools.
                if result.text:
                    last_text = result.text
            else:
                # Exhausted step_limit without a tool-free reply.
                self.finished = False
        finally:
            end_python_sandbox()

        return AgentRunResult(
            assistant_text=last_text,
            messages=list(self.messages),
            usage=_sum_usage(usages),
            steps=list(self.steps),
            finished=self.finished,
            step_count=len(self.steps),
        )
