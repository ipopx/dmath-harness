"""CLI entrypoints for the D-MATH harness."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dmath_harness.agent import DEFAULT_STEP_LIMIT
from dmath_harness.agent_run import run_agent_exam
from dmath_harness.baseline import run_baseline
from dmath_harness.client import ChatClient, load_config, load_judge_config
from dmath_harness.exam import load_exam
from dmath_harness.judge import grade_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dmath_harness",
        description="D-MATH open-LLM exam harness",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    baseline = sub.add_parser("baseline", help="No-harness baseline runners")
    baseline_sub = baseline.add_subparsers(dest="baseline_command", required=True)

    run = baseline_sub.add_parser("run", help="Single-prompt run over an exam JSON")
    run.add_argument(
        "--exam",
        type=Path,
        required=True,
        help="Path to exam JSON (e.g. data/exams/dmath-mock-2024-hs.json)",
    )
    run.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSONL path (default: runs/baseline_<exam_id>_<timestamp>.jsonl)",
    )
    run.add_argument(
        "--question-id",
        action="append",
        dest="question_ids",
        default=None,
        help="Restrict to one or more question ids (repeatable)",
    )
    run.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="Path to env file (default: .env)",
    )

    agent = sub.add_parser("agent", help="ReAct harnessed agent runners")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)

    agent_run = agent_sub.add_parser(
        "run",
        help="ReAct agent run over an exam JSON (calculator / run_python tools)",
    )
    agent_run.add_argument(
        "--exam",
        type=Path,
        required=True,
        help="Path to exam JSON (e.g. data/exams/dmath-mock-2024-hs.json)",
    )
    agent_run.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSONL path (default: runs/agent_<exam_id>_<timestamp>.jsonl)",
    )
    agent_run.add_argument(
        "--question-id",
        action="append",
        dest="question_ids",
        default=None,
        help="Restrict to one or more question ids (repeatable)",
    )
    agent_run.add_argument(
        "--step-limit",
        type=int,
        default=DEFAULT_STEP_LIMIT,
        help=f"Max ReAct steps per question (default: {DEFAULT_STEP_LIMIT})",
    )
    agent_run.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="Path to env file (default: .env)",
    )

    grade = sub.add_parser("grade", help="Grade trajectories against an exam")
    grade_sub = grade.add_subparsers(dest="grade_command", required=True)

    grade_run = grade_sub.add_parser(
        "run",
        help="Hybrid grade: exact/numeric extractors + holistic LLM judge",
    )
    grade_run.add_argument("--exam", type=Path, required=True, help="Exam JSON path")
    grade_run.add_argument(
        "--trajectories",
        type=Path,
        required=True,
        help="Baseline JSONL path",
    )
    grade_run.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output grade JSON (default: runs/grades_<exam_id>_<timestamp>.json)",
    )
    grade_run.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="Path to env file (default: .env)",
    )
    grade_run.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip LLM judge (MCQ/numeric only; method/proof get 0)",
    )

    args = parser.parse_args(argv)

    if args.command == "baseline" and args.baseline_command == "run":
        return _cmd_baseline_run(args)
    if args.command == "agent" and args.agent_command == "run":
        return _cmd_agent_run(args)
    if args.command == "grade" and args.grade_command == "run":
        return _cmd_grade_run(args)

    parser.error(f"Unhandled command: {args.command}")
    return 2


def _cmd_baseline_run(args: argparse.Namespace) -> int:
    config = load_config(env_file=args.env_file if Path(args.env_file).exists() else None)
    exam = load_exam(args.exam)
    client = ChatClient(config)

    if args.out is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.out = Path("runs") / f"baseline_{exam.exam_id}_{stamp}.jsonl"

    out_path = run_baseline(
        exam,
        client,
        args.out,
        question_ids=args.question_ids,
    )
    print(f"Wrote trajectories to {out_path}")
    print(f"model={config.model} base_url={config.base_url} questions={len(exam.questions)}")
    return 0


def _cmd_agent_run(args: argparse.Namespace) -> int:
    config = load_config(env_file=args.env_file if Path(args.env_file).exists() else None)
    exam = load_exam(args.exam)
    client = ChatClient(config)

    if args.out is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.out = Path("runs") / f"agent_{exam.exam_id}_{stamp}.jsonl"

    out_path = run_agent_exam(
        exam,
        client,
        args.out,
        question_ids=args.question_ids,
        step_limit=args.step_limit,
    )
    n = len(args.question_ids) if args.question_ids else len(exam.questions)
    print(f"Wrote trajectories to {out_path}")
    print(
        f"model={config.model} base_url={config.base_url} "
        f"questions={n} step_limit={args.step_limit} harness=react"
    )
    return 0


def _cmd_grade_run(args: argparse.Namespace) -> int:
    env_file = args.env_file if Path(args.env_file).exists() else None
    exam = load_exam(args.exam)

    judge_client = None
    if not args.no_judge:
        judge_config = load_judge_config(env_file=env_file)
        judge_client = ChatClient(judge_config)

    if args.out is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.out = Path("runs") / f"grades_{exam.exam_id}_{stamp}.json"

    out_path = grade_files(
        args.exam,
        args.trajectories,
        judge_client,
        args.out,
    )
    report = json.loads(out_path.read_text(encoding="utf-8"))
    print(f"Wrote grades to {out_path}")
    print(
        f"points={report['points_awarded']}/{report['total_points']} "
        f"({report['percent']}%) "
        f"judge_model={report.get('judge_model')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
