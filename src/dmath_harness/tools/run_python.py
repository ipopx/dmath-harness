"""Run plain Python in a Docker math sandbox (session-reused per agent run)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

DEFAULT_IMAGE = "dmath-python-sandbox:latest"
DEFAULT_TIMEOUT_S = 15.0
DEFAULT_MEMORY = "256m"
DEFAULT_CPUS = "1"
DEFAULT_PIDS_LIMIT = "64"
DEFAULT_MAX_OUTPUT_CHARS = 12_000
DEFAULT_DOCKER_START_TIMEOUT_S = 120.0

_READY = "__DMATH_READY__"
_END = "__DMATH_END__"
_DONE = "__DMATH_DONE__"
_EXIT = "__DMATH_EXIT__"

# Persistent REPL inside the container: shared globals across run_python calls.
# READY once at boot; each request is code lines + END, then DONE.
_REPL_DRIVER = f"""
import sys
import traceback

_NS = {{"__name__": "__sandbox__"}}
print({_READY!r}, flush=True)
while True:
    _buf = []
    while True:
        _line = sys.stdin.readline()
        if not _line:
            raise SystemExit(0)
        if _line.rstrip("\\n") == {_END!r}:
            break
        if _line.rstrip("\\n") == {_EXIT!r}:
            raise SystemExit(0)
        _buf.append(_line)
    _code = "".join(_buf)
    try:
        exec(compile(_code, "<sandbox>", "exec"), _NS, _NS)
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
    print({_DONE!r}, flush=True)
"""

RUN_PYTHON_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_python",
        "description": (
            "Execute plain Python code in an isolated sandbox and return stdout/stderr. "
            "Print results explicitly (e.g. print(...)). Available: Python stdlib, numpy, sympy. "
            "State (imports/variables) persists across calls within the same agent question."
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

# Cache successful docker readiness within a process so we only start/build once.
_docker_ready_bin: str | None = None
_docker_ensure_attempted = False

# Per agent-question session (set after PythonSandboxSession is defined).
_session_wanted = False
_active_session = None  # PythonSandboxSession | None


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


def _sandbox_context_dir() -> Path | None:
    """Locate ``docker/python-sandbox`` for image builds."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "docker" / "python-sandbox",
        Path.cwd() / "docker" / "python-sandbox",
    ]
    for path in candidates:
        if (path / "Dockerfile").is_file():
            return path
    return None


def _find_docker() -> str | None:
    which = shutil.which("docker")
    if which:
        return which
    home = Path.home()
    candidates = [
        "/usr/local/bin/docker",
        "/opt/homebrew/bin/docker",
        str(home / ".docker" / "bin" / "docker"),
        "/Applications/Docker.app/Contents/Resources/bin/docker",
    ]
    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def _docker_daemon_ready(docker_bin: str) -> bool:
    try:
        probe = subprocess.run(
            [docker_bin, "info"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def _try_start_docker_engine() -> None:
    """Best-effort: launch Docker Desktop or Colima if present."""
    docker_app = Path("/Applications/Docker.app")
    if docker_app.is_dir() and sys.platform == "darwin":
        subprocess.run(
            ["open", "-a", "Docker"],
            capture_output=True,
            text=True,
            check=False,
        )

    colima = shutil.which("colima")
    if colima:
        subprocess.run(
            [colima, "start"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )


def _wait_for_daemon(docker_bin: str, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _docker_daemon_ready(docker_bin):
            return True
        time.sleep(1.5)
    return False


def _image_present(docker_bin: str, image: str) -> bool:
    try:
        probe = subprocess.run(
            [docker_bin, "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def _build_sandbox_image(docker_bin: str, image: str) -> str | None:
    """Build the sandbox image; return an error string on failure, else None."""
    context = _sandbox_context_dir()
    if context is None:
        return (
            f"Error: docker image {image!r} missing and could not find "
            "docker/python-sandbox/Dockerfile to build it"
        )
    try:
        built = subprocess.run(
            [docker_bin, "build", "-t", image, str(context)],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "Error: timed out building docker sandbox image"
    except OSError as exc:
        return f"Error: failed to build docker sandbox image: {exc}"
    if built.returncode != 0:
        detail = (built.stderr or built.stdout or "").strip() or f"exit {built.returncode}"
        return f"Error: docker build failed: {_truncate(detail, 2000)}"
    return None


def ensure_docker(image: str | None = None) -> str | None:
    """
    Ensure a usable ``docker`` CLI + daemon + sandbox image.

    Returns the docker binary path on success, or ``None`` if Docker cannot be
    brought up.
    """
    global _docker_ready_bin, _docker_ensure_attempted

    image = image or _env("DMATH_PYTHON_SANDBOX_IMAGE", DEFAULT_IMAGE)
    if _docker_ready_bin and _image_present(_docker_ready_bin, image):
        return _docker_ready_bin

    docker_bin = _find_docker()
    if docker_bin is None:
        if not _docker_ensure_attempted and Path("/Applications/Docker.app").is_dir():
            _docker_ensure_attempted = True
            _try_start_docker_engine()
            try:
                timeout_s = float(
                    _env(
                        "DMATH_PYTHON_SANDBOX_DOCKER_START_TIMEOUT_S",
                        str(DEFAULT_DOCKER_START_TIMEOUT_S),
                    )
                )
            except ValueError:
                timeout_s = DEFAULT_DOCKER_START_TIMEOUT_S
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                docker_bin = _find_docker()
                if docker_bin and _docker_daemon_ready(docker_bin):
                    break
                time.sleep(1.5)
            else:
                return None
        else:
            return None

    if not _docker_daemon_ready(docker_bin):
        if not _docker_ensure_attempted:
            _docker_ensure_attempted = True
            _try_start_docker_engine()
        try:
            timeout_s = float(
                _env(
                    "DMATH_PYTHON_SANDBOX_DOCKER_START_TIMEOUT_S",
                    str(DEFAULT_DOCKER_START_TIMEOUT_S),
                )
            )
        except ValueError:
            timeout_s = DEFAULT_DOCKER_START_TIMEOUT_S
        if not _wait_for_daemon(docker_bin, timeout_s):
            return None

    if not _image_present(docker_bin, image):
        err = _build_sandbox_image(docker_bin, image)
        if err is not None:
            return None

    _docker_ready_bin = docker_bin
    return docker_bin


def reset_docker_ensure_state() -> None:
    """Test helper: clear process-level docker readiness cache."""
    global _docker_ready_bin, _docker_ensure_attempted
    _docker_ready_bin = None
    _docker_ensure_attempted = False


def _format_process_output(stdout: str, stderr: str) -> str:
    combined = stdout or ""
    if stderr.strip():
        combined = (
            f"{stdout}{stderr}"
            if stdout.endswith("\n") or not stdout
            else f"{stdout}\n{stderr}"
        )
    return combined


def _resource_kwargs() -> tuple[str, str, str, str]:
    image = _env("DMATH_PYTHON_SANDBOX_IMAGE", DEFAULT_IMAGE)
    memory = _env("DMATH_PYTHON_SANDBOX_MEMORY", DEFAULT_MEMORY)
    cpus = _env("DMATH_PYTHON_SANDBOX_CPUS", DEFAULT_CPUS)
    pids = _env("DMATH_PYTHON_SANDBOX_PIDS_LIMIT", DEFAULT_PIDS_LIMIT)
    return image, memory, cpus, pids


def _timeout_and_max_chars() -> tuple[float, int]:
    try:
        timeout_s = float(_env("DMATH_PYTHON_SANDBOX_TIMEOUT_S", str(DEFAULT_TIMEOUT_S)))
    except ValueError:
        timeout_s = DEFAULT_TIMEOUT_S
    try:
        max_chars = int(_env("DMATH_PYTHON_SANDBOX_MAX_OUTPUT", str(DEFAULT_MAX_OUTPUT_CHARS)))
    except ValueError:
        max_chars = DEFAULT_MAX_OUTPUT_CHARS
    return timeout_s, max_chars


class PythonSandboxSession:
    """One long-lived Docker container with a stateful Python REPL for a question."""

    def __init__(
        self,
        docker_bin: str,
        *,
        image: str,
        memory: str,
        cpus: str,
        pids: str,
        timeout_s: float,
        max_chars: int,
    ) -> None:
        self.docker_bin = docker_bin
        self.image = image
        self.memory = memory
        self.cpus = cpus
        self.pids = pids
        self.timeout_s = timeout_s
        self.max_chars = max_chars
        self.container_name = f"dmath-py-{uuid.uuid4().hex[:12]}"
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> str | None:
        """Start the container+REPL. Return an error string on failure, else None."""
        cmd = [
            self.docker_bin,
            "run",
            "-i",
            "--rm",
            "--name",
            self.container_name,
            "--network",
            "none",
            "--memory",
            self.memory,
            "--cpus",
            self.cpus,
            "--pids-limit",
            self.pids,
            self.image,
            "python",
            "-u",
            "-c",
            _REPL_DRIVER,
        ]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            return "Error: docker executable not found on PATH"
        except OSError as exc:
            return f"Error: failed to start docker sandbox: {exc}"

        ready = self._readline_until_marker(_READY, self.timeout_s)
        if ready is None:
            self.stop()
            return "Error: timed out waiting for docker sandbox REPL to become ready"
        if isinstance(ready, str) and ready.startswith("Error:"):
            self.stop()
            return ready
        return None

    def execute(self, code: str) -> str:
        with self._lock:
            if not self.alive or self._proc is None or self._proc.stdin is None:
                return "Error: docker sandbox session is not running"

            try:
                self._proc.stdin.write(code if code.endswith("\n") else code + "\n")
                self._proc.stdin.write(_END + "\n")
                self._proc.stdin.flush()
            except OSError as exc:
                return f"Error: failed to write to docker sandbox: {exc}"

            lines = self._read_until_marker(_DONE, self.timeout_s)
            if lines is None:
                self.stop()
                return f"Error: execution timed out after {self.timeout_s:g}s"
            if isinstance(lines, str) and lines.startswith("Error:"):
                return lines

            # Drop the trailing DONE marker; keep printed output / tracebacks.
            body = "\n".join(lines[:-1] if lines and lines[-1] == _DONE else lines)
            if not body.strip():
                return "(no output — print results explicitly, e.g. print(...))"
            return _truncate(body.rstrip("\n"), self.max_chars)

    def stop(self) -> None:
        """Stop the REPL and remove the container (``docker run --rm``)."""
        proc = self._proc
        self._proc = None
        if proc is None:
            return

        try:
            if proc.poll() is None and proc.stdin is not None:
                try:
                    proc.stdin.write(_EXIT + "\n")
                    proc.stdin.write(_END + "\n")
                    proc.stdin.flush()
                except OSError:
                    pass
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        finally:
            # Belt-and-suspenders: force-remove if still around.
            try:
                subprocess.run(
                    [self.docker_bin, "rm", "-f", self.container_name],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass

    def _readline_until_marker(self, marker: str, timeout_s: float) -> list[str] | str | None:
        return self._read_until_marker(marker, timeout_s)

    def _read_until_marker(self, marker: str, timeout_s: float) -> list[str] | str | None:
        """Read stdout lines until ``marker``. None = timeout; str Error = dead process."""
        assert self._proc is not None and self._proc.stdout is not None
        lines: list[str] = []
        deadline = time.monotonic() + timeout_s

        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                # Drain whatever is left.
                rest = self._proc.stdout.read() or ""
                detail = "\n".join([*lines, *rest.splitlines()]).strip()
                return (
                    f"Error: docker sandbox exited unexpectedly"
                    + (f": {_truncate(detail, self.max_chars)}" if detail else "")
                )
            # Use a short select-like wait via readline in a worker if needed;
            # for simplicity, set a small poll by reading with remaining time via threads.
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            line_holder: list[str | None] = [None]
            err_holder: list[BaseException | None] = [None]

            def _read() -> None:
                try:
                    line_holder[0] = self._proc.stdout.readline()  # type: ignore[union-attr]
                except BaseException as exc:  # noqa: BLE001
                    err_holder[0] = exc

            t = threading.Thread(target=_read, daemon=True)
            t.start()
            t.join(timeout=min(remaining, 0.5))
            if t.is_alive():
                continue
            if err_holder[0] is not None:
                return f"Error: failed reading docker sandbox output: {err_holder[0]}"
            line = line_holder[0]
            if line is None or line == "":
                if self._proc.poll() is not None:
                    return "Error: docker sandbox exited unexpectedly"
                continue
            text = line.rstrip("\n")
            lines.append(text)
            if text == marker:
                return lines

        return None


def begin_python_sandbox() -> None:
    """Mark the start of an agent question; container is started lazily on first use."""
    global _session_wanted
    _session_wanted = True


def end_python_sandbox() -> None:
    """Tear down the question-scoped sandbox container (always, even if unfinished)."""
    global _session_wanted, _active_session
    _session_wanted = False
    if _active_session is not None:
        _active_session.stop()
        _active_session = None


def _ensure_active_session() -> PythonSandboxSession | str:
    """Return the active session, or an error string."""
    global _active_session

    if _active_session is not None and _active_session.alive:
        return _active_session

    image, memory, cpus, pids = _resource_kwargs()
    timeout_s, max_chars = _timeout_and_max_chars()
    docker_bin = ensure_docker(image)
    if docker_bin is None:
        return (
            "Error: docker CLI/daemon/image could not be brought up. "
            "Install Docker Desktop (or Colima), ensure `docker` is on PATH, "
            "then retry (the harness will auto-start the engine and build "
            f"{image!r} from docker/python-sandbox)."
        )

    session = PythonSandboxSession(
        docker_bin,
        image=image,
        memory=memory,
        cpus=cpus,
        pids=pids,
        timeout_s=timeout_s,
        max_chars=max_chars,
    )
    err = session.start()
    if err is not None:
        return err
    _active_session = session
    return session


def _execute_docker_oneshot(
    docker_bin: str,
    code: str,
    *,
    image: str,
    memory: str,
    cpus: str,
    pids: str,
    timeout_s: float,
    max_chars: int,
) -> str:
    """Ephemeral ``docker run --rm`` (used when no agent session is open, e.g. unit tests)."""
    cmd = [
        docker_bin,
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

    combined = _format_process_output(completed.stdout or "", completed.stderr or "")

    if completed.returncode != 0:
        detail = combined.strip() or f"exit code {completed.returncode}"
        if "Unable to find image" in detail or "pull access denied" in detail:
            build_err = _build_sandbox_image(docker_bin, image)
            if build_err is not None:
                return build_err
            try:
                completed = subprocess.run(
                    cmd,
                    input=code,
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return f"Error: docker retry failed: {exc}"
            combined = _format_process_output(
                completed.stdout or "", completed.stderr or ""
            )
            if completed.returncode != 0:
                detail = combined.strip() or f"exit code {completed.returncode}"
                return (
                    f"Error: python exited with code {completed.returncode}: "
                    f"{_truncate(detail, max_chars)}"
                )
        else:
            return (
                f"Error: python exited with code {completed.returncode}: "
                f"{_truncate(detail, max_chars)}"
            )

    if not combined.strip():
        return "(no output — print results explicitly, e.g. print(...))"
    return _truncate(combined.rstrip("\n"), max_chars)


def execute_python(code: str) -> str:
    """Run code in Docker (session REPL during an agent question; else one-shot)."""
    if not code.strip():
        return "Error: empty code"

    if _session_wanted:
        session = _ensure_active_session()
        if isinstance(session, str):
            return session
        return session.execute(code)

    image, memory, cpus, pids = _resource_kwargs()
    timeout_s, max_chars = _timeout_and_max_chars()
    docker_bin = ensure_docker(image)
    if docker_bin is None:
        return (
            "Error: docker CLI/daemon/image could not be brought up. "
            "Install Docker Desktop (or Colima), ensure `docker` is on PATH, "
            "then retry (the harness will auto-start the engine and build "
            f"{image!r} from docker/python-sandbox)."
        )

    return _execute_docker_oneshot(
        docker_bin,
        code,
        image=image,
        memory=memory,
        cpus=cpus,
        pids=pids,
        timeout_s=timeout_s,
        max_chars=max_chars,
    )


def run_python(arguments: dict[str, Any]) -> str:
    code = arguments.get("code")
    if not isinstance(code, str):
        return "Error: 'code' must be a string"
    return execute_python(code)
