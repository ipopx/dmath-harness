"""Live agent / baseline execution for the Streamlit UI."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dmath_harness.agent import DEFAULT_STEP_LIMIT, Agent
from dmath_harness.baseline import build_messages
from dmath_harness.client import ChatClient, ChatConfig, load_config, load_judge_config
from dmath_harness.exam import Exam, Question
from dmath_harness.judge import grade_exam
from dmath_harness.ui.io_helpers import RUNS_DIR, write_trajectories


ProgressFn = Callable[[str], None]


def make_client(model: str, *, env_file: str | None = ".env") -> ChatClient:
    base = load_config(env_file=env_file if env_file and Path(env_file).exists() else None)
    config: ChatConfig = replace(base, model=model)
    return ChatClient(config)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_from_agent(
    exam: Exam,
    question: Question,
    agent_result: Any,
    *,
    run_id: str,
    client: ChatClient,
    step_limit: int,
) -> dict[str, Any]:
    total_latency = sum(float(s.get("latency_ms") or 0.0) for s in agent_result.steps)
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
        "messages": agent_result.messages,
        "assistant_text": agent_result.assistant_text,
        "usage": agent_result.usage.to_dict(),
        "latency_ms": round(total_latency, 2),
        "finish_reason": (
            agent_result.steps[-1]["finish_reason"] if agent_result.steps else None
        ),
        "timestamp": _utc_now_iso(),
        "harness": "react",
        "finished": agent_result.finished,
        "step_count": agent_result.step_count,
        "step_limit": step_limit,
        "steps": agent_result.steps,
    }


def run_agent_questions(
    exam: Exam,
    question_ids: list[str],
    client: ChatClient,
    *,
    step_limit: int = DEFAULT_STEP_LIMIT,
    on_progress: ProgressFn | None = None,
) -> list[dict[str, Any]]:
    wanted = set(question_ids)
    selected = [q for q in exam.questions if q.id in wanted]
    missing = wanted - {q.id for q in selected}
    if missing:
        raise ValueError(f"Unknown question id(s): {sorted(missing)}")

    run_id = uuid.uuid4().hex[:12]
    agent = Agent(client, step_limit=step_limit)
    records: list[dict[str, Any]] = []
    for question in selected:
        if on_progress:
            on_progress(f"Solving {question.id} ({question.type}, {question.points} pts)…")
        result = agent.run(question)
        records.append(
            _record_from_agent(
                exam,
                question,
                result,
                run_id=run_id,
                client=client,
                step_limit=step_limit,
            )
        )
    return records


def run_baseline_questions(
    exam: Exam,
    question_ids: list[str],
    client: ChatClient,
    *,
    on_progress: ProgressFn | None = None,
) -> list[dict[str, Any]]:
    """One-shot baseline for selected questions (no tools)."""
    wanted = set(question_ids)
    selected = [q for q in exam.questions if q.id in wanted]
    missing = wanted - {q.id for q in selected}
    if missing:
        raise ValueError(f"Unknown question id(s): {sorted(missing)}")

    run_id = uuid.uuid4().hex[:12]
    records: list[dict[str, Any]] = []
    for question in selected:
        if on_progress:
            on_progress(f"Solving {question.id} (baseline)…")
        messages = build_messages(question)
        chat = client.chat(messages)
        records.append(
            {
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
                + [
                    chat.assistant_message
                    if chat.assistant_message
                    else {"role": "assistant", "content": chat.text}
                ],
                "assistant_text": chat.text,
                "usage": chat.usage.to_dict(),
                "latency_ms": round(chat.latency_ms, 2),
                "finish_reason": chat.raw_finish_reason,
                "timestamp": _utc_now_iso(),
                "harness": "baseline",
            }
        )
    return records


def grade_records(
    exam: Exam,
    records: list[dict[str, Any]],
    *,
    use_judge: bool = True,
    env_file: str | None = ".env",
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    judge_client = None
    if use_judge:
        if on_progress:
            on_progress("Loading judge client…")
        env = env_file if env_file and Path(env_file).exists() else None
        judge_client = ChatClient(load_judge_config(env_file=env))
    if on_progress:
        on_progress("Grading trajectories…")
    return grade_exam(exam, records, judge_client)


def default_out_path(harness: str, model: str, exam_id: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_model = (
        model.replace("/", "_").replace(":", "_").replace(".", "").replace("-", "")[:40]
    )
    return RUNS_DIR / f"{harness}_{safe_model}_{exam_id}_{stamp}.jsonl"


__all__ = [
    "default_out_path",
    "grade_records",
    "make_client",
    "run_agent_questions",
    "run_baseline_questions",
    "write_trajectories",
]
