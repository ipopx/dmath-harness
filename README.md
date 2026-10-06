# D-MATH Harness

Compare a bare open-weight LLM against a harnessed agent on ETH **D-MATH**
(Department of Mathematics) exam problems.

## Phase 1.1 — No-harness baseline

Thin OpenAI-compatible chat client + single-prompt runner over exam JSON.
Local development targets **Apertus 8B** via Ollama; later the same code points
at the **CSCS Inference API** by changing `.env` only.

### Local Apertus 8B (size)

| | Approx. |
|--|--|
| Download (Q4 quantized) | ~4.7–5.5 GB disk |
| Full BF16 weights | ~16–17 GB disk |
| Runtime (Q4 + overhead) | ~6 GB memory |
| Comfortable Mac | 16 GB unified memory |

### Setup

```bash
pixi install
cp .env.example .env
# Install Ollama, pull an Apertus 8B instruct tag, set MODEL in .env
```

Ollama serves an OpenAI-compatible API at `http://127.0.0.1:11434/v1`.

### Run baseline on the mock exam

```bash
pixi run baseline-mock
# or:
PYTHONPATH=src pixi run python -m dmath_harness baseline run \
  --exam data/exams/dmath-mock-2024-hs.json
```

Trajectories are written under `runs/` (gitignored) as JSONL: one record per
question with messages, assistant text, token usage, and latency.

### CSCS later

When you have a CSCS Inference API key:

```env
OPENAI_BASE_URL=https://api.inference.cscs.ch/v1
OPENAI_API_KEY=<CSCS_INFERENCE_API_KEY>
MODEL=swiss-ai/Apertus-v1.5-8B
```

List models available to your key with `GET /v1/models` on that base URL.
