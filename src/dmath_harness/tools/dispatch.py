"""Tool registry and recoverable dispatch."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from dmath_harness.tools.calculator import CALCULATOR_SCHEMA, run_calculator
from dmath_harness.tools.run_python import RUN_PYTHON_SCHEMA, run_python

ToolHandler = Callable[[dict[str, Any]], str]

# Drop a (schema, handler) pair here to disable that tool for the agent.
TOOL_REGISTRY: list[tuple[dict[str, Any], ToolHandler]] = [
    (CALCULATOR_SCHEMA, run_calculator),
    (RUN_PYTHON_SCHEMA, run_python),
]

TOOL_SCHEMAS: list[dict[str, Any]] = [schema for schema, _ in TOOL_REGISTRY]

_HANDLERS: dict[str, ToolHandler] = {
    schema["function"]["name"]: handler for schema, handler in TOOL_REGISTRY
}


def dispatch_tool_call(name: str, arguments_json: str) -> str:
    """Run a tool by name; never raise — return an error string on failure."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"Error: unknown tool {name!r}"

    try:
        arguments = json.loads(arguments_json) if arguments_json.strip() else {}
    except json.JSONDecodeError as exc:
        return f"Error: malformed tool arguments JSON: {exc.msg}"

    if not isinstance(arguments, dict):
        return "Error: tool arguments must be a JSON object"

    try:
        return handler(arguments)
    except Exception as exc:  # noqa: BLE001 — recoverable for the agent loop
        return f"Error: tool {name!r} failed: {exc}"
