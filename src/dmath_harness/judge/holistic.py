"""Holistic LLM judge for proofs and free-text method credit."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from dmath_harness.agent import DEFAULT_STEP_LIMIT, Agent
from dmath_harness.client import ChatClient
from dmath_harness.tools import TOOL_SCHEMAS

JUDGE_SYSTEM = """\
You are a strict but fair mathematics exam grader for ETH D-MATH.
Award partial credit when the student shows correct ideas, even if the writeup
differs from the reference (many valid proofs/solutions exist).
Do NOT solve the problem from scratch; only grade the student answer.
You may use tools to verify the student's arithmetic or code (same as the exam agent):
- calculator: quick pure arithmetic expressions
- run_python: execute Python (stdlib, numpy, sympy); print results explicitly
When you are done (including after any tool use), reply with your grade and do not \
call tools. Your final reply must be ONLY a single JSON object (no markdown fences, \
no extra text):
{"points_awarded": <number>, "max_points": <number>, "rationale": "<short>"}
points_awarded must be between 0 and max_points inclusive.
"""


@dataclass(frozen=True)
class JudgeAward:
    points_awarded: float
    max_points: float
    rationale: str
    raw_text: str
    parse_error: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "points_awarded": self.points_awarded,
            "max_points": self.max_points,
            "rationale": self.rationale,
            "parse_error": self.parse_error,
            "raw_text": self.raw_text,
        }


def holistic_judge(
    client: ChatClient,
    *,
    question_prompt: str,
    reference_answer: str,
    key_ideas: list[str] | None,
    student_answer: str,
    max_points: float,
    rubric_hint: str | None = None,
    step_limit: int = DEFAULT_STEP_LIMIT,
    tools: list[dict[str, Any]] | None = None,
) -> JudgeAward:
    """Run a tool-enabled ReAct judge; return a holistic score in ``0..max_points``."""
    tool_schemas = list(TOOL_SCHEMAS) if tools is None else tools
    user_content = _build_user_prompt(
        question_prompt=question_prompt,
        reference_answer=reference_answer,
        key_ideas=key_ideas,
        student_answer=student_answer,
        max_points=max_points,
        rubric_hint=rubric_hint,
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    agent = Agent(
        client,
        step_limit=step_limit,
        system_prompt=JUDGE_SYSTEM,
        tools=tool_schemas,
    )
    run = agent.run_from_messages(messages)
    award = parse_award(run.assistant_text, max_points=max_points)
    if award.parse_error:
        retry_messages = run.messages + [
            {
                "role": "user",
                "content": (
                    "Your previous reply was not valid JSON. "
                    f'Reply with ONLY: {{"points_awarded": <0..{max_points}>, '
                    f'"max_points": {max_points}, "rationale": "..."}}'
                ),
            },
        ]
        retry_run = agent.run_from_messages(retry_messages)
        award = parse_award(retry_run.assistant_text, max_points=max_points)
    return award


def _build_user_prompt(
    *,
    question_prompt: str,
    reference_answer: str,
    key_ideas: list[str] | None,
    student_answer: str,
    max_points: float,
    rubric_hint: str | None,
) -> str:
    ideas = ""
    if key_ideas:
        bullets = "\n".join(f"- {idea}" for idea in key_ideas)
        ideas = f"\nKey ideas (award credit for equivalent approaches):\n{bullets}\n"
    hint = f"\nRubric hint: {rubric_hint}\n" if rubric_hint else ""
    return (
        f"Max points: {max_points}\n"
        f"{hint}"
        f"Question:\n{question_prompt}\n\n"
        f"Reference solution:\n{reference_answer}\n"
        f"{ideas}\n"
        f"Student answer:\n{student_answer}\n"
    )


_JSON_RE = re.compile(r"\{[\s\S]*\}")


def parse_award(text: str, *, max_points: float) -> JudgeAward:
    """Parse judge JSON into a ``JudgeAward`` (clamped to ``max_points``)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    match = _JSON_RE.search(cleaned)
    if not match:
        return JudgeAward(
            points_awarded=0.0,
            max_points=max_points,
            rationale="Judge output was not valid JSON.",
            raw_text=text,
            parse_error=True,
        )
    try:
        data = json.loads(match.group(0))
        awarded = float(data.get("points_awarded", 0))
        rationale = str(data.get("rationale", "")).strip() or "(no rationale)"
    except (json.JSONDecodeError, TypeError, ValueError):
        return JudgeAward(
            points_awarded=0.0,
            max_points=max_points,
            rationale="Judge output was not valid JSON.",
            raw_text=text,
            parse_error=True,
        )

    awarded = max(0.0, min(float(max_points), awarded))
    return JudgeAward(
        points_awarded=awarded,
        max_points=max_points,
        rationale=rationale,
        raw_text=text,
        parse_error=False,
    )


# Back-compat alias used in tests
_parse_award = parse_award
