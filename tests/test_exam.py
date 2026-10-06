from pathlib import Path

from dmath_harness.baseline import build_messages, build_user_prompt
from dmath_harness.exam import load_exam

ROOT = Path(__file__).resolve().parents[1]
MOCK_EXAM = ROOT / "data" / "exams" / "dmath-mock-2024-hs.json"


def test_load_mock_exam():
    exam = load_exam(MOCK_EXAM)
    assert exam.exam_id == "dmath-mock-2024-hs"
    assert exam.department == "D-MATH"
    assert len(exam.questions) == 3
    assert exam.questions[0].type == "mcq"
    assert exam.questions[0].choices is not None
    assert "A" in exam.questions[0].choices


def test_mcq_user_prompt_includes_choices():
    exam = load_exam(MOCK_EXAM)
    q1 = exam.questions[0]
    user = build_user_prompt(q1)
    assert "Choices:" in user
    assert "A." in user
    messages = build_messages(q1)
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
