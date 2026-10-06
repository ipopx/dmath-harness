"""Hybrid grader: deterministic extractors + holistic LLM judge."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dmath_harness.client import ChatClient
from dmath_harness.exam import Exam, Question, load_exam
from dmath_harness.judge.extract import (
    extract_final_number,
    extract_mcq_letter,
    numbers_equal,
)
from dmath_harness.judge.holistic import JudgeAward, holistic_judge


JudgeFn = Callable[..., JudgeAward]


def load_trajectories(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}") from exc
    return records


def grade_exam(
    exam: Exam,
    trajectories: list[dict[str, Any]],
    judge_client: ChatClient | None,
    *,
    judge_fn: JudgeFn | None = None,
) -> dict[str, Any]:
    """Grade trajectories against an exam; return a score report dict."""
    by_id = {t["question_id"]: t for t in trajectories if "question_id" in t}
    judge = judge_fn or holistic_judge
    question_results: list[dict[str, Any]] = []

    for question in exam.questions:
        traj = by_id.get(question.id)
        if traj is None:
            question_results.append(
                {
                    "question_id": question.id,
                    "type": question.type,
                    "grading": "missing",
                    "points_awarded": 0.0,
                    "max_points": float(question.points),
                    "rationale": "No trajectory for this question.",
                    "topic": question.topic,
                    "difficulty": question.difficulty,
                }
            )
            continue
        student = traj.get("assistant_text") or ""
        if question.type == "mcq":
            result = _grade_mcq(question, student)
        elif question.type == "short_answer":
            result = _grade_short_answer(question, student, judge_client, judge)
        elif question.type == "proof":
            result = _grade_proof(question, student, judge_client, judge)
        else:
            result = {
                "question_id": question.id,
                "type": question.type,
                "grading": "unsupported",
                "points_awarded": 0.0,
                "max_points": float(question.points),
                "rationale": f"Unsupported question type: {question.type}",
                "topic": question.topic,
                "difficulty": question.difficulty,
            }
        question_results.append(result)

    total_max = float(exam.total_points) if exam.total_points is not None else sum(
        q.points for q in exam.questions
    )
    total_awarded = sum(float(q["points_awarded"]) for q in question_results)
    percent = (100.0 * total_awarded / total_max) if total_max else 0.0

    by_topic: dict[str, dict[str, float]] = defaultdict(lambda: {"awarded": 0.0, "max": 0.0})
    by_difficulty: dict[str, dict[str, float]] = defaultdict(
        lambda: {"awarded": 0.0, "max": 0.0}
    )
    for q in question_results:
        by_topic[q["topic"]]["awarded"] += float(q["points_awarded"])
        by_topic[q["topic"]]["max"] += float(q["max_points"])
        by_difficulty[q["difficulty"]]["awarded"] += float(q["points_awarded"])
        by_difficulty[q["difficulty"]]["max"] += float(q["max_points"])

    solver_model = next((t.get("model") for t in trajectories if t.get("model")), None)
    run_id = next((t.get("run_id") for t in trajectories if t.get("run_id")), None)

    return {
        "exam_id": exam.exam_id,
        "run_id": run_id,
        "model": solver_model,
        "judge_model": judge_client.config.model if judge_client else None,
        "total_points": total_max,
        "points_awarded": total_awarded,
        "percent": round(percent, 2),
        # Placeholder until course-specific cutoffs are known.
        "eth_grade_stub": _eth_grade_stub(percent),
        "questions": question_results,
        "by_topic": dict(by_topic),
        "by_difficulty": dict(by_difficulty),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def grade_files(
    exam_path: str | Path,
    trajectories_path: str | Path,
    judge_client: ChatClient | None,
    out_path: str | Path,
    *,
    judge_fn: JudgeFn | None = None,
) -> Path:
    exam = load_exam(exam_path)
    trajectories = load_trajectories(trajectories_path)
    report = grade_exam(exam, trajectories, judge_client, judge_fn=judge_fn)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _grade_mcq(question: Question, student: str) -> dict[str, Any]:
    valid = set(question.choices.keys()) if question.choices else None
    predicted = extract_mcq_letter(student, valid=valid)
    expected = str(question.reference.get("answer", "")).upper()
    correct = predicted is not None and predicted == expected
    awarded = float(question.points) if correct else 0.0
    return {
        "question_id": question.id,
        "type": question.type,
        "grading": "exact_match",
        "points_awarded": awarded,
        "max_points": float(question.points),
        "predicted": predicted,
        "expected": expected,
        "rationale": (
            f"Extracted {predicted!r}; expected {expected!r}."
            if predicted
            else "Could not extract a choice letter."
        ),
        "topic": question.topic,
        "difficulty": question.difficulty,
    }


def _grade_short_answer(
    question: Question,
    student: str,
    judge_client: ChatClient | None,
    judge: JudgeFn,
) -> dict[str, Any]:
    numeric_pts = sum(s.points for s in question.steps if s.grading == "numeric_exact")
    method_pts = sum(s.points for s in question.steps if s.grading == "llm_judge")
    if numeric_pts == 0 and method_pts == 0:
        numeric_pts = float(question.points)

    expected = question.reference.get("answer")
    predicted = extract_final_number(student)
    numeric_ok = numbers_equal(predicted, expected)
    numeric_awarded = float(numeric_pts) if numeric_ok else 0.0

    method_awarded = 0.0
    method_detail: dict[str, Any] | None = None
    if method_pts > 0:
        if judge_client is None:
            method_detail = {
                "points_awarded": 0.0,
                "max_points": float(method_pts),
                "rationale": "No judge client configured.",
                "parse_error": True,
            }
        else:
            award = judge(
                judge_client,
                question_prompt=question.prompt,
                reference_answer=str(
                    question.reference.get("derivation")
                    or question.reference.get("answer")
                    or ""
                ),
                key_ideas=None,
                student_answer=student,
                max_points=float(method_pts),
                rubric_hint=(
                    "Grade only whether the student used a correct method "
                    "(e.g. combinations / binomial coefficient). "
                    "Do not grade the final numeric value here."
                ),
            )
            method_awarded = award.points_awarded
            method_detail = award.to_dict()

    total = numeric_awarded + method_awarded
    parts = [
        f"numeric: predicted={predicted!r} expected={expected!r} → {numeric_awarded}/{numeric_pts}"
    ]
    if method_detail:
        parts.append(
            f"method: {method_detail.get('points_awarded')}/{method_pts} "
            f"({method_detail.get('rationale')})"
        )

    return {
        "question_id": question.id,
        "type": question.type,
        "grading": "numeric_exact+holistic_llm" if method_pts else "numeric_exact",
        "points_awarded": total,
        "max_points": float(question.points),
        "predicted": predicted,
        "expected": expected,
        "numeric_points_awarded": numeric_awarded,
        "numeric_points_max": float(numeric_pts),
        "method": method_detail,
        "rationale": "; ".join(parts),
        "topic": question.topic,
        "difficulty": question.difficulty,
    }


def _grade_proof(
    question: Question,
    student: str,
    judge_client: ChatClient | None,
    judge: JudgeFn,
) -> dict[str, Any]:
    max_points = float(question.points)
    if judge_client is None:
        return {
            "question_id": question.id,
            "type": question.type,
            "grading": "holistic_llm",
            "points_awarded": 0.0,
            "max_points": max_points,
            "rationale": "No judge client configured.",
            "topic": question.topic,
            "difficulty": question.difficulty,
        }

    key_ideas = question.reference.get("key_ideas")
    if key_ideas is not None and not isinstance(key_ideas, list):
        key_ideas = [str(key_ideas)]

    award = judge(
        judge_client,
        question_prompt=question.prompt,
        reference_answer=str(question.reference.get("answer", "")),
        key_ideas=key_ideas,
        student_answer=student,
        max_points=max_points,
        rubric_hint=(
            "Holistic proof grade: credit any correct proof strategy equivalent "
            "to the reference; do not require matching the official writeup verbatim."
        ),
    )
    return {
        "question_id": question.id,
        "type": question.type,
        "grading": "holistic_llm",
        "points_awarded": award.points_awarded,
        "max_points": max_points,
        "rationale": award.rationale,
        "parse_error": award.parse_error,
        "judge_raw": award.raw_text,
        "topic": question.topic,
        "difficulty": question.difficulty,
    }


def _eth_grade_stub(percent: float) -> float | None:
    """Temporary linear map 0–100% → 1.0–6.0. Not an official D-MATH scale."""
    return round(1.0 + 5.0 * (percent / 100.0), 2)
