"""Tests for run_python tool and Docker sandbox."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from dmath_harness.tools.dispatch import TOOL_SCHEMAS, dispatch_tool_call
from dmath_harness.tools.run_python import (
    DEFAULT_IMAGE,
    RUN_PYTHON_SCHEMA,
    execute_python,
    run_python,
)


def test_run_python_schema_registered():
    names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert "run_python" in names
    assert "calculator" in names
    assert RUN_PYTHON_SCHEMA["function"]["name"] == "run_python"


def test_run_python_argument_validation():
    assert run_python({"code": 123}).startswith("Error:")
    assert run_python({}).startswith("Error:")
    assert execute_python("").startswith("Error:")
    assert execute_python("   ").startswith("Error:")


def test_dispatch_run_python_malformed_json():
    assert dispatch_tool_call("run_python", "not-json").startswith("Error:")


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        probe = subprocess.run(
            ["docker", "image", "inspect", DEFAULT_IMAGE],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


docker_required = pytest.mark.skipif(
    not _docker_ready(),
    reason=f"docker image {DEFAULT_IMAGE!r} not available",
)


@docker_required
@pytest.mark.docker
def test_execute_python_print():
    out = execute_python("print(2 + 2)")
    assert out.strip() == "4"


@docker_required
@pytest.mark.docker
def test_execute_python_sympy_factorial():
    out = execute_python("import sympy\nprint(sympy.factorial(12))")
    assert out.strip() == "479001600"


@docker_required
@pytest.mark.docker
def test_execute_python_syntax_error_recoverable():
    out = execute_python("def (")
    assert out.startswith("Error:")


@docker_required
@pytest.mark.docker
def test_dispatch_run_python_happy_path():
    result = dispatch_tool_call(
        "run_python",
        '{"code": "import numpy as np\\nprint(int(np.sum([1, 2, 3])))"}',
    )
    assert result.strip() == "6"
