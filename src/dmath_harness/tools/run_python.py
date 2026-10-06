"""Run plain Python in an ephemeral Docker math sandbox."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

DEFAULT_IMAGE = "dmath-python-sandbox:latest"
DEFAULT_TIMEOUT_S = 15.0
DEFAULT_MEMORY = "256m"
DEFAULT_CPUS = "1"
DEFAULT_PIDS_LIMIT = "64"
DEFAULT_MAX_OUTPUT_CHARS = 12_000

RUN_PYTHON_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_python",
        "description": (
            "Execute plain Python code in an isolated sandbox and return stdout/stderr. "
            "Print results explicitly (e.g. print(...)). Available: Python stdlib, numpy, sympy."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python source to run, e.g. 'import sympy; print(sympy.factorial(10))'.",
                },
            },
            "required": ["code"],
        },
    },
}


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return text[:max_chars] + f"\n...[truncated {omitted} chars]"


def execute_python(code: str) -> str:
    """Run code in an ephemeral Docker container; return output or an Error string."""
    if not code.strip():
        return "Error: empty code"

    if shutil.which("docker") is None:
        return "Error: docker executable not found on PATH"

    image = _env("DMATH_PYTHON_SANDBOX_IMAGE", DEFAULT_IMAGE)
    memory = _env("DMATH_PYTHON_SANDBOX_MEMORY", DEFAULT_MEMORY)
    cpus = _env("DMATH_PYTHON_SANDBOX_CPUS", DEFAULT_CPUS)
    pids = _env("DMATH_PYTHON_SANDBOX_PIDS_LIMIT", DEFAULT_PIDS_LIMIT)
    try:
        timeout_s = float(_env("DMATH_PYTHON_SANDBOX_TIMEOUT_S", str(DEFAULT_TIMEOUT_S)))
    except ValueError:
        timeout_s = DEFAULT_TIMEOUT_S
    try:
        max_chars = int(_env("DMATH_PYTHON_SANDBOX_MAX_OUTPUT", str(DEFAULT_MAX_OUTPUT_CHARS)))
    except ValueError:
        max_chars = DEFAULT_MAX_OUTPUT_CHARS

    cmd = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "--memory",
        memory,
        "--cpus",
        cpus,
        "--pids-limit",
        pids,
        image,
        "python",
        "-u",
        "-",
    ]

    try:
        completed = subprocess.run(
            cmd,
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"Error: execution timed out after {timeout_s:g}s"
    except FileNotFoundError:
        return "Error: docker executable not found on PATH"
    except OSError as exc:
        return f"Error: failed to start docker: {exc}"

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    combined = stdout
    if stderr.strip():
        combined = f"{stdout}{stderr}" if stdout.endswith("\n") or not stdout else f"{stdout}\n{stderr}"

    if completed.returncode != 0:
        detail = combined.strip() or f"exit code {completed.returncode}"
        # Common docker failure: image missing
        if "Unable to find image" in detail or "pull access denied" in detail:
            return (
                f"Error: docker image {image!r} not found. "
                f"Build with: docker build -t {image} docker/python-sandbox"
            )
        return f"Error: python exited with code {completed.returncode}: {_truncate(detail, max_chars)}"

    if not combined.strip():
        return "(no output — print results explicitly, e.g. print(...))"
    return _truncate(combined.rstrip("\n"), max_chars)


def run_python(arguments: dict[str, Any]) -> str:
    code = arguments.get("code")
    if not isinstance(code, str):
        return "Error: 'code' must be a string"
    return execute_python(code)
