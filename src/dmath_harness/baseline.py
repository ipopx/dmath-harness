"""No-harness baseline: one chat completion per exam question."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from dmath_harness.client import ChatClient
from dmath_harness.exam import Exam, Question


SYSTEM_PROMPT = """\
You are solving an ETH Zurich D-MATH (Department of Mathematics) exam question.
Answer in the same language as the question.
Follow these output conventions:
- Multiple choice: state your reasoning briefly, then end with a single line \
`Final answer: X` where X is the choice letter (A, B, C, ...).
- Short answer / numeric: show a brief derivation, then end with \
`Final answer: <value>`.
- Proof: write a clear, structured proof. There is no separate final-answer line.
Do not use tools. Solve from the given information only.
"""


def build_user_prompt(question: Question) -> str:
    parts = [question.prompt.strip()]
    if question.type == "mcq" and question.choices:
        parts.append("")
        parts.append("Choices:")
        for key in sorted(question.choices.keys()):
            parts.append(f"  {key}. {question.choices[key]}")
    return "\n".join(parts)


def build_messages(question: Question) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(question)},
    ]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_baseline(
    exam: Exam,
    client: ChatClient,
    out_path: Path,
    *,
    question_ids: list[str] | None = None,
    run_id: str | None = None,
) -> Path:
    """Run a single-prompt baseline over exam items; write JSONL trajectories."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = run_id or uuid.uuid4().hex[:12]

    selected = exam.questions
    if question_ids is not None:
        wanted = set(question_ids)
        selected = [q for q in exam.questions if q.id in wanted]
        missing = wanted - {q.id for q in selected}
        if missing:
            raise ValueError(f"Unknown question id(s): {sorted(missing)}")

    with out_path.open("w", encoding="utf-8") as f:
        for question in selected:
            record = _solve_one(exam, question, client, run_id)
            _write_jsonl(f, record)

    return out_path


def _solve_one(
    exam: Exam,
    question: Question,
    client: ChatClient,
    run_id: str,
) -> dict[str, Any]:
    messages = build_messages(question)
    result = client.chat(messages)
    return {
        "run_id": run_id,
        "exam_id": exam.exam_id,
        "question_id": question.id,
        "question_type": question.type,
        "topic": question.topic,
        "difficulty": question.difficulty,
        "points": question.points,
        "model": client.config.model,
        "base_url": client.config.base_url,
        "messages": messages
        + [{"role": "assistant", "content": result.text}],
        "assistant_text": result.text,
        "usage": result.usage.to_dict(),
        "latency_ms": round(result.latency_ms, 2),
        "finish_reason": result.raw_finish_reason,
        "timestamp": _utc_now_iso(),
        "harness": "none",
    }


def _write_jsonl(stream: TextIO, record: dict[str, Any]) -> None:
    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    stream.flush()
