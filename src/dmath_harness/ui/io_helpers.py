"""Filesystem helpers for exams, trajectories, and grades."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dmath_harness.judge import load_trajectories

ROOT = Path(__file__).resolve().parents[3]
EXAMS_DIR = ROOT / "data" / "exams"
RUNS_DIR = ROOT / "runs"

MODEL_PRESETS: dict[str, str] = {
    "Llama 3.2 3B": "llama3.2:3b",
    "Apertus 8B (Ollama Q4)": "MichelRosselli/apertus:8b-instruct-2509-q4_k_m",
}


def list_exam_paths() -> list[Path]:
    if not EXAMS_DIR.is_dir():
        return []
    return sorted(EXAMS_DIR.glob("*.json"))


def list_trajectory_paths(*, harness: str | None = None) -> list[Path]:
    if not RUNS_DIR.is_dir():
        return []
    paths = sorted(RUNS_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if harness == "agent":
        paths = [p for p in paths if p.name.startswith("agent_")]
    elif harness == "baseline":
        paths = [p for p in paths if p.name.startswith("baseline_")]
    return paths


def list_grade_paths() -> list[Path]:
    if not RUNS_DIR.is_dir():
        return []
    return sorted(RUNS_DIR.glob("grades_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def load_grade_report(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def grade_by_question(report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not report:
        return {}
    return {q["question_id"]: q for q in report.get("questions", []) if "question_id" in q}


def find_matching_grades(traj_path: Path) -> Path | None:
    """Best-effort match: grades_<stem>.json or grades that share stem tokens."""
    stem = traj_path.stem  # e.g. agent_llama32_3b_mock
    candidates = [
        RUNS_DIR / f"grades_{stem}.json",
        RUNS_DIR / f"grades_{stem.removeprefix('agent_').removeprefix('baseline_')}.json",
    ]
    for c in candidates:
        if c.is_file():
            return c
    # Fuzzy: any grades file whose name contains the trajectory stem after prefix
    key = stem
    for p in list_grade_paths():
        if key in p.stem or p.stem.replace("grades_", "") in key:
            return p
    return None


def summarize_trajectories(records: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = completion = total = 0
    latency = 0.0
    steps = 0
    for r in records:
        usage = r.get("usage") or {}
        prompt += int(usage.get("prompt_tokens") or 0)
        completion += int(usage.get("completion_tokens") or 0)
        total += int(usage.get("total_tokens") or 0)
        latency += float(r.get("latency_ms") or 0.0)
        steps += int(r.get("step_count") or 0)
    return {
        "n_questions": len(records),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "latency_ms": round(latency, 2),
        "step_count": steps,
    }


def write_trajectories(records: list[dict[str, Any]], out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return out_path


__all__ = [
    "EXAMS_DIR",
    "MODEL_PRESETS",
    "ROOT",
    "RUNS_DIR",
    "find_matching_grades",
    "grade_by_question",
    "list_exam_paths",
    "list_grade_paths",
    "list_trajectory_paths",
    "load_grade_report",
    "load_trajectories",
    "summarize_trajectories",
    "write_trajectories",
]
