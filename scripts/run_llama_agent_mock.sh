#!/usr/bin/env bash
# Re-run llama3.2:3b agent on the mock exam (requires Docker Desktop running).
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="${HOME}/.docker/bin:/usr/local/bin:/opt/homebrew/bin:${PATH}"
export PYTHONPATH=src
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://127.0.0.1:11434/v1}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-ollama}"
export TEMPERATURE="${TEMPERATURE:-0}"
export OPENAI_TIMEOUT_S="${OPENAI_TIMEOUT_S:-300}"
export MODEL=llama3.2:3b

echo "== docker =="
docker info >/dev/null
docker image inspect dmath-python-sandbox:latest >/dev/null 2>&1 \
  || docker build -t dmath-python-sandbox:latest docker/python-sandbox

echo "== smoke run_python session =="
.pixi/envs/default/bin/python - <<'PY'
from dmath_harness.tools.run_python import (
    begin_python_sandbox,
    end_python_sandbox,
    execute_python,
)
import subprocess

begin_python_sandbox()
try:
    print("call1", repr(execute_python("import sympy; print(sympy.factorial(12))")))
    print("call2 stateful", repr(execute_python("y = 7\nprint(y)")))
    print("call3 stateful", repr(execute_python("print(y * 6)")))
    ps = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    print("containers during session:", ps.stdout.strip().splitlines())
finally:
    end_python_sandbox()
ps2 = subprocess.run(
    ["docker", "ps", "--format", "{{.Names}}"],
    capture_output=True,
    text=True,
    check=False,
)
print("containers after end:", [n for n in ps2.stdout.splitlines() if n.startswith("dmath-py-")])
PY

echo "== agent mock =="
.pixi/envs/default/bin/python -m dmath_harness agent run \
  --exam data/exams/dmath-mock-2024-hs.json \
  --out runs/agent_llama32_3b_mock.jsonl

echo "== Q5 tool result =="
.pixi/envs/default/bin/python - <<'PY'
import json
from pathlib import Path
rows = [json.loads(l) for l in Path("runs/agent_llama32_3b_mock.jsonl").read_text().splitlines() if l.strip()]
for r in rows:
    if r["question_id"] != "Q5":
        continue
    tools = [m.get("content") for m in r["messages"] if m.get("role") == "tool"]
    print("Q5 tool results:", tools)
    print("finished:", r.get("finished"), "steps:", r.get("step_count"))
    print("answer head:", (r.get("assistant_text") or "")[:180])
PY

echo "== leftover dmath containers (should be empty) =="
docker ps --format '{{.Names}}' | grep '^dmath-py-' || echo '(none)'
echo DONE
