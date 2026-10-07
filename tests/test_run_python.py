"""Tests for run_python tool and Docker sandbox."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from dmath_harness.tools.dispatch import TOOL_SCHEMAS, dispatch_tool_call
from dmath_harness.tools import run_python as run_python_mod
from dmath_harness.tools.run_python import (
    DEFAULT_IMAGE,
    RUN_PYTHON_SCHEMA,
    begin_python_sandbox,
    end_python_sandbox,
    execute_python,
    reset_docker_ensure_state,
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


def test_errors_when_docker_unavailable(monkeypatch):
    reset_docker_ensure_state()
    monkeypatch.setattr(run_python_mod, "ensure_docker", lambda image=None: None)
    out = execute_python("print(1)")
    assert out.startswith("Error: docker CLI/daemon/image could not be brought up")

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


@docker_required
@pytest.mark.docker
def test_session_reuses_container_and_state():
    begin_python_sandbox()
    try:
        out1 = execute_python("x = 41\nprint('ok')")
        assert "ok" in out1
        out2 = execute_python("print(x + 1)")
        assert out2.strip() == "42"
        listed = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert any(name.startswith("dmath-py-") for name in listed.stdout.splitlines())
    finally:
        end_python_sandbox()

    listed_after = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert not any(
        name.startswith("dmath-py-") for name in listed_after.stdout.splitlines()
    )
