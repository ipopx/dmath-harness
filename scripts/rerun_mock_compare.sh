#!/usr/bin/env bash
# Full mock compare: 4 trajectories + grades + plots.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="${HOME}/.docker/bin:/usr/local/bin:/opt/homebrew/bin:${PATH}"
export PYTHONPATH=src
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://127.0.0.1:11434/v1}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-ollama}"
export TEMPERATURE="${TEMPERATURE:-0}"
export OPENAI_TIMEOUT_S="${OPENAI_TIMEOUT_S:-300}"
APERTUS='MichelRosselli/apertus:8b-instruct-2509-q4_k_m'
LLAMA='llama3.2:3b'
export JUDGE_MODEL="$APERTUS"
export JUDGE_TEMPERATURE=0
EXAM=data/exams/dmath-mock-2024-hs.json
PY="${PY:-.pixi/envs/default/bin/python}"

echo "== docker image =="
docker info >/dev/null
docker image inspect dmath-python-sandbox:latest >/dev/null 2>&1 \
  || docker build -t dmath-python-sandbox:latest docker/python-sandbox

run_traj() {
  local model="$1" mode="$2" out="$3"
  echo "==== $mode $model -> $out ===="
  MODEL="$model" "$PY" -m dmath_harness "$mode" run --exam "$EXAM" --out "$out"
}

run_traj "$APERTUS" baseline runs/baseline_apertus8b_mock.jsonl
run_traj "$APERTUS" agent    runs/agent_apertus8b_mock.jsonl
run_traj "$LLAMA"   baseline runs/baseline_llama32_3b_mock.jsonl
run_traj "$LLAMA"   agent    runs/agent_llama32_3b_mock.jsonl

grade_one() {
  local traj="$1" out="$2"
  echo "==== grade $traj -> $out ===="
  MODEL="$APERTUS" "$PY" -m dmath_harness grade run \
    --exam "$EXAM" --trajectories "$traj" --out "$out"
}

grade_one runs/baseline_apertus8b_mock.jsonl  runs/grades_baseline_apertus8b_mock.json
grade_one runs/agent_apertus8b_mock.jsonl     runs/grades_agent_apertus8b_mock.json
grade_one runs/baseline_llama32_3b_mock.jsonl runs/grades_baseline_llama32_3b_mock.json
grade_one runs/agent_llama32_3b_mock.jsonl    runs/grades_agent_llama32_3b_mock.json

echo "==== plots ===="
mkdir -p plots .matplotlib
MPLCONFIGDIR="$PWD/.matplotlib" PYTHONPATH=".vendor:src" "$PY" - <<'PY'
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

conds = [
  ("Apertus 8B", "baseline", "runs/baseline_apertus8b_mock.jsonl", "runs/grades_baseline_apertus8b_mock.json"),
  ("Apertus 8B", "agent", "runs/agent_apertus8b_mock.jsonl", "runs/grades_agent_apertus8b_mock.json"),
  ("Llama 3.2 3B", "baseline", "runs/baseline_llama32_3b_mock.jsonl", "runs/grades_baseline_llama32_3b_mock.json"),
  ("Llama 3.2 3B", "agent", "runs/agent_llama32_3b_mock.jsonl", "runs/grades_agent_llama32_3b_mock.json"),
]

def metrics(traj_path: str) -> dict:
    rows = [json.loads(l) for l in Path(traj_path).read_text().splitlines() if l.strip()]
    lat = sum(float(r.get("latency_ms") or 0) for r in rows)
    toks = sum((r.get("usage") or {}).get("total_tokens") or 0 for r in rows)
    tool_calls = 0
    for r in rows:
        for s in r.get("steps") or []:
            tool_calls += int(s.get("n_tool_calls") or 0)
    return {"latency_ms": lat, "total_tokens": toks, "tool_calls": tool_calls}

out = []
for model, harness, traj, grade in conds:
    m = metrics(traj)
    g = json.loads(Path(grade).read_text())
    row = {
        "model": model,
        "harness": harness,
        **m,
        "points_awarded": g["points_awarded"],
        "total_points": g["total_points"],
        "percent": g["percent"],
        "judge_model": g.get("judge_model"),
    }
    out.append(row)
    print(
        f"{model:14} {harness:8} lat={m['latency_ms']:.0f}ms "
        f"tools={m['tool_calls']} toks={m['total_tokens']} "
        f"pts={g['points_awarded']}/{g['total_points']} ({g['percent']}%)"
    )

Path("plots/mock_compare_metrics.json").write_text(json.dumps(out, indent=2))

models = ["Apertus 8B", "Llama 3.2 3B"]
harnesses = ["baseline", "agent"]
labels = {"baseline": "No harness", "agent": "Agent + tools"}
colors = {"baseline": "#4C78A8", "agent": "#F58518"}

def lookup(model: str, harness: str) -> dict:
    for row in out:
        if row["model"] == model and row["harness"] == harness:
            return row
    raise KeyError((model, harness))

def grouped_bars(ax, values_by_harness, ylabel, title, fmt=None):
    x = np.arange(len(models))
    width = 0.35
    for i, h in enumerate(harnesses):
        vals = [values_by_harness[h][m] for m in models]
        bars = ax.bar(x + (i - 0.5) * width, vals, width, label=labels[h], color=colors[h])
        for bar, v in zip(bars, vals):
            ax.annotate(
                fmt(v) if fmt else f"{v:g}",
                xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
            )
    ax.set_xticks(x)
    ax.set_xticklabels(models)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

fig1, axes = plt.subplots(1, 3, figsize=(12.5, 4.2))
latency = {h: {m: lookup(m, h)["latency_ms"] / 1000.0 for m in models} for h in harnesses}
tools = {h: {m: lookup(m, h)["tool_calls"] for m in models} for h in harnesses}
tokens = {h: {m: lookup(m, h)["total_tokens"] for m in models} for h in harnesses}

grouped_bars(axes[0], latency, "Total latency (s)", "Total latency", fmt=lambda v: f"{v:.1f}")
grouped_bars(axes[1], tools, "Tool calls", "Total tool calls", fmt=lambda v: f"{int(v)}")
grouped_bars(axes[2], tokens, "Total tokens", "Total tokens", fmt=lambda v: f"{int(v)}")

fig1.suptitle("Mock exam efficiency (Q1–Q5) — solver trajectories", fontsize=12, y=1.02)
fig1.tight_layout()
fig1.savefig("plots/mock_efficiency_llama_vs_apertus.png", dpi=160, bbox_inches="tight")
fig1.savefig("plots/mock_efficiency_llama_vs_apertus.pdf", bbox_inches="tight")
plt.close(fig1)

fig2, ax = plt.subplots(figsize=(7.2, 4.5))
points = {h: {m: lookup(m, h)["points_awarded"] for m in models} for h in harnesses}
percents = {h: {m: lookup(m, h)["percent"] for m in models} for h in harnesses}
total = lookup(models[0], "baseline")["total_points"]
x = np.arange(len(models))
width = 0.35
for i, h in enumerate(harnesses):
    vals = [points[h][m] for m in models]
    pcts = [percents[h][m] for m in models]
    bars = ax.bar(x + (i - 0.5) * width, vals, width, label=labels[h], color=colors[h])
    for bar, v, p in zip(bars, vals, pcts):
        ax.annotate(
            f"{v:g}/{total:g}\n({p:.0f}%)",
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )
ax.axhline(total, color="#888888", linestyle="--", linewidth=1, label=f"Max ({total:g})")
ax.set_xticks(x)
ax.set_xticklabels(models)
ax.set_ylabel("Points awarded")
ax.set_ylim(0, total * 1.25)
ax.set_title("Mock exam scores (Q1–Q5)\nAgent judge with tools (shared Apertus judge)")
ax.legend(frameon=False)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
fig2.tight_layout()
fig2.savefig("plots/mock_scores_llama_vs_apertus.png", dpi=160, bbox_inches="tight")
fig2.savefig("plots/mock_scores_llama_vs_apertus.pdf", bbox_inches="tight")
plt.close(fig2)
print("plots refreshed")
PY

echo DONE
