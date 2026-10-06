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

### Tests (no model needed)

```bash
PYTHONPATH=src pixi run --environment dev pytest -q
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
