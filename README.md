# D-MATH Harness

Compare a bare open-weight LLM against a harnessed agent on ETH **D-MATH**
(Department of Mathematics) exam problems.

## Phase 1.1 — Reproduce the local Apertus baseline

This runs a **no-harness** baseline: one chat completion per exam question, no
tools. Trajectories land in `runs/*.jsonl`.

### Prerequisites

- macOS (Apple Silicon recommended) or Linux
- ~6 GB free RAM while the model runs; ~5 GB disk for the download
- [pixi](https://pixi.sh) (`curl -fsSL https://pixi.sh/install.sh | bash`)
- [Ollama](https://ollama.com) (macOS: download the app, or use their install script)

### 1. Clone and install Python deps

```bash
cd dmath-harness
pixi install
cp .env.example .env
```

`.env` should look like this (already set in `.env.example`):

```env
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_API_KEY=ollama
MODEL=MichelRosselli/apertus:8b-instruct-2509-q4_k_m
TEMPERATURE=0
OPENAI_TIMEOUT_S=300
```

### 2. Start Ollama and pull Apertus 8B

```bash
# macOS: open the Ollama app once so the API listens on :11434
open -a Ollama

# Community Q4 GGUF of Apertus-8B-Instruct (~5.1 GB, first time only)
ollama pull MichelRosselli/apertus:8b-instruct-2509-q4_k_m
```

Check the server:

```bash
curl -s http://127.0.0.1:11434/api/tags
```

### 3. Run the baseline on the mock exam

```bash
pixi run baseline-mock
```

Equivalent explicit command (writes a timestamped file under `runs/`):

```bash
PYTHONPATH=src pixi run python -m dmath_harness baseline run \
  --exam data/exams/dmath-mock-2024-hs.json
```

Pin the output path:

```bash
PYTHONPATH=src pixi run python -m dmath_harness baseline run \
  --exam data/exams/dmath-mock-2024-hs.json \
  --out runs/baseline_apertus8b_mock.jsonl
```

Optional: only one question

```bash
PYTHONPATH=src pixi run python -m dmath_harness baseline run \
  --exam data/exams/dmath-mock-2024-hs.json \
  --question-id Q1
```

### 4. Inspect results

Each line of the JSONL is one question: `assistant_text`, `usage`, `latency_ms`,
full `messages`, `model`, etc.

```bash
# quick peek
python -c "
import json
from pathlib import Path
p = sorted(Path('runs').glob('baseline_*.jsonl'))[-1]
for line in p.read_text().splitlines():
    r = json.loads(line)
    print(r['question_id'], r['usage'], r['assistant_text'][:200], '...\n')
"
```

### Model size (local Q4)

| | Approx. |
|--|--|
| Download | ~5.1 GB disk |
| Runtime | ~6 GB memory |
| Comfortable Mac | 16 GB unified memory |

Note: the Ollama tag is a **community GGUF** of Apertus 8B Instruct, not the
CSCS-hosted `swiss-ai/Apertus-v1.5-*` checkpoint. Re-run on CSCS for official
cross-model comparisons.

### 5. Grade a baseline run (Phase 0.2 hybrid grader)

Scores trajectories against the exam JSON:

- **MCQ** — deterministic letter extract + exact match
- **Short answer** — numeric exact match + holistic LLM judge for method points
- **Proof** — holistic LLM judge (one score for the whole proof; not step-wise)

Uses the same OpenAI-compatible stack; optional `JUDGE_MODEL` in `.env`
(defaults to `MODEL`). The holistic judge runs in the same ReAct `Agent` wrapper
as the solver, with the same tools (`calculator`, `run_python`).

```bash
# requires runs/baseline_apertus8b_mock.jsonl from step 3
pixi run grade-mock
```

Or explicitly:

```bash
PYTHONPATH=src pixi run python -m dmath_harness grade run \
  --exam data/exams/dmath-mock-2024-hs.json \
  --trajectories runs/baseline_apertus8b_mock.jsonl \
  --out runs/grades_apertus8b_mock.json
```

Deterministic-only (skip LLM judge; method/proof get 0):

```bash
PYTHONPATH=src pixi run python -m dmath_harness grade run \
  --exam data/exams/dmath-mock-2024-hs.json \
  --trajectories runs/baseline_apertus8b_mock.jsonl \
  --out runs/grades_deterministic_only.json \
  --no-judge
```

## Phase 1.2 / 1.3 — ReAct agent with tools

The harnessed agent uses the same OpenAI-compatible client, plus a ReAct loop
with function tools:

- **`calculator`** — safe arithmetic (restricted AST)
- **`run_python`** — plain Python in an ephemeral Docker sandbox (numpy, sympy)

Tools are registered in `src/dmath_harness/tools/dispatch.py`. Drop a
`(schema, handler)` pair there (or pass a custom `tools=` list into `Agent`) to
disable a tool.

### Python sandbox (`run_python`)

Requires **Docker**. During each agent question the harness keeps **one** sandbox
container alive (stateful Python REPL reused across `run_python` calls) and
removes it when that question’s ReAct loop ends (`finished` or step-limit). On
first use it also brings Docker up if needed (locate the CLI, start Desktop /
Colima, wait for the daemon, and build `dmath-python-sandbox:latest` from
`docker/python-sandbox` when missing). There is no local-process fallback.

Install Docker Desktop for Mac: https://docs.docker.com/desktop/setup/install/mac-install/
Then open the app once, and (optional if auto-build works):

```bash
docker build -t dmath-python-sandbox:latest docker/python-sandbox
```

Sandbox knobs are in `.env.example` (`DMATH_PYTHON_SANDBOX_*`).

### Run the agent

```bash
pixi run agent-mock
```

Or pin model / question / output (llama3.2 is useful for debugging tool calls):

```bash
MODEL=llama3.2:3b PYTHONPATH=src pixi run python -m dmath_harness agent run \
  --exam data/exams/dmath-mock-2024-hs.json \
  --question-id Q5 \
  --out runs/agent_llama32_3b_q5_python.jsonl
```

Mock probes: **Q4** forces `calculator`; **Q5** forces `run_python` (sympy).

Trajectories and grade JSON are written under `runs/` (gitignored).

### Tests (no model needed)

```bash
PYTHONPATH=src pixi run --environment dev pytest -q
```

Docker-backed `run_python` tests need the sandbox image (build step above):

```bash
PYTHONPATH=src pixi run --environment dev pytest -q -m docker
```

### CSCS later (same client)

When you have a CSCS Inference API key, only change `.env`:

```env
OPENAI_BASE_URL=https://api.inference.cscs.ch/v1
OPENAI_API_KEY=<CSCS_INFERENCE_API_KEY>
MODEL=swiss-ai/Apertus-v1.5-8B
```

Then run the same `pixi run baseline-mock` command. List models with
`GET https://api.inference.cscs.ch/v1/models`.
