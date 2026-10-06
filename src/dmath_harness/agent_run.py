"""Harnessed ReAct agent runner over exam questions."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from dmath_harness.agent import DEFAULT_STEP_LIMIT, Agent
from dmath_harness.client import ChatClient
from dmath_harness.exam import Exam, Question


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_agent_exam(
    exam: Exam,
    client: ChatClient,
    out_path: Path,
    *,
    question_ids: list[str] | None = None,
    run_id: str | None = None,
    step_limit: int = DEFAULT_STEP_LIMIT,
) -> Path:
    """Run the ReAct agent over exam items; write JSONL trajectories."""
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

    agent = Agent(client, step_limit=step_limit)
    with out_path.open("w", encoding="utf-8") as f:
        for question in selected:
            record = _solve_one(exam, question, agent, run_id, client)
            _write_jsonl(f, record)

    return out_path


def _solve_one(
    exam: Exam,
    question: Question,
    agent: Agent,
    run_id: str,
    client: ChatClient,
) -> dict[str, Any]:
    result = agent.run(question)
    total_latency = sum(float(s.get("latency_ms") or 0.0) for s in result.steps)
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
        "messages": result.messages,
        "assistant_text": result.assistant_text,
        "usage": result.usage.to_dict(),
        "latency_ms": round(total_latency, 2),
        "finish_reason": (
            result.steps[-1]["finish_reason"] if result.steps else None
        ),
        "timestamp": _utc_now_iso(),
        "harness": "react",
        "finished": result.finished,
        "step_count": result.step_count,
        "step_limit": agent.step_limit,
        "steps": result.steps,
    }


def _write_jsonl(stream: TextIO, record: dict[str, Any]) -> None:
    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    stream.flush()
