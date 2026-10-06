"""Exam JSON schema and loader for Phase-0 structured D-MATH items."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class Step(BaseModel):
    id: str
    description: str
    points: float
    topic: str
    grading: str
    expected: Any = None


class Question(BaseModel):
    id: str
    type: Literal["mcq", "short_answer", "proof", "coding"]
    topic: str
    difficulty: Literal["easy", "medium", "hard"]
    language: str = "en"
    points: float
    prompt: str
    choices: dict[str, str] | None = None
    reference: dict[str, Any] = Field(default_factory=dict)
    steps: list[Step] = Field(default_factory=list)


class Exam(BaseModel):
    exam_id: str
    department: str | None = None
    course: str | None = None
    course_code: str | None = None
    institution: str | None = None
    term: str | None = None
    language: str = "en"
    total_points: float | None = None
    notes: str | None = None
    questions: list[Question]


def load_exam(path: str | Path) -> Exam:
    """Load and validate an exam JSON file."""
    exam_path = Path(path)
    with exam_path.open(encoding="utf-8") as f:
        data = json.load(f)
    return Exam.model_validate(data)
