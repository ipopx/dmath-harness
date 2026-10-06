"""CLI entrypoints for the D-MATH harness."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from dmath_harness.baseline import run_baseline
from dmath_harness.client import ChatClient
from dmath_harness.config import load_config
from dmath_harness.exam import load_exam


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

    args = parser.parse_args(argv)

    if args.command == "baseline" and args.baseline_command == "run":
        return _cmd_baseline_run(args)

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


if __name__ == "__main__":
    sys.exit(main())
