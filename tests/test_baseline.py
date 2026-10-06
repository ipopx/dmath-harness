from dmath_harness.baseline import build_messages
from dmath_harness.client import ChatClient, ChatResult, Usage
from dmath_harness.config import ChatConfig
from dmath_harness.baseline import run_baseline
from dmath_harness.exam import load_exam
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOCK_EXAM = ROOT / "data" / "exams" / "dmath-mock-2024-hs.json"


class FakeClient(ChatClient):
    def __init__(self) -> None:
        self.config = ChatConfig(
            base_url="http://test.local/v1",
            api_key="test",
            model="fake-model",
        )

    def chat(self, messages):  # type: ignore[override]
        assert messages[0]["role"] == "system"
        return ChatResult(
            text="Final answer: A",
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            latency_ms=1.5,
            raw_finish_reason="stop",
        )


def test_run_baseline_writes_jsonl(tmp_path: Path):
    exam = load_exam(MOCK_EXAM)
    out = tmp_path / "traj.jsonl"
    run_baseline(exam, FakeClient(), out, question_ids=["Q1"])
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "fake-model" in lines[0]
    assert "Q1" in lines[0]
