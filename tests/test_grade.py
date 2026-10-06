from pathlib import Path

from dmath_harness.client import ChatClient, ChatConfig
from dmath_harness.exam import load_exam
from dmath_harness.judge import JudgeAward, grade_exam
from dmath_harness.judge.holistic import parse_award

ROOT = Path(__file__).resolve().parents[1]
MOCK_EXAM = ROOT / "data" / "exams" / "dmath-mock-2024-hs.json"


def _fake_traj(qid: str, text: str) -> dict:
    return {
        "run_id": "test",
        "exam_id": "dmath-mock-2024-hs",
        "question_id": qid,
        "model": "fake-solver",
        "assistant_text": text,
    }


def test_parse_award_json():
    award = parse_award(
        '{"points_awarded": 4, "max_points": 10, "rationale": "partial"}',
        max_points=10,
    )
    assert award.points_awarded == 4
    assert not award.parse_error


def test_parse_award_clamps():
    award = parse_award(
        '{"points_awarded": 99, "max_points": 10, "rationale": "too high"}',
        max_points=10,
    )
    assert award.points_awarded == 10


def test_grade_mcq_and_numeric_without_judge():
    exam = load_exam(MOCK_EXAM)
    trajectories = [
        _fake_traj("Q1", "Thinking...\nFinal answer: A"),
        _fake_traj("Q2", "C(10,3)=120\nFinal answer: 120"),
        _fake_traj("Q3", "Proof incomplete."),
    ]
    report = grade_exam(exam, trajectories, judge_client=None)
    by_id = {q["question_id"]: q for q in report["questions"]}
    assert by_id["Q1"]["points_awarded"] == 4
    assert by_id["Q2"]["numeric_points_awarded"] == 4
    assert by_id["Q2"]["points_awarded"] == 4  # method skipped without judge
    assert by_id["Q3"]["points_awarded"] == 0
    assert report["total_points"] == exam.total_points


def test_grade_with_fake_judge():
    exam = load_exam(MOCK_EXAM)

    def fake_judge(client, **kwargs):
        return JudgeAward(
            points_awarded=kwargs["max_points"],
            max_points=kwargs["max_points"],
            rationale="full credit (fake)",
            raw_text="{}",
        )

    dummy = ChatClient(
        ChatConfig(base_url="http://test.local/v1", api_key="x", model="fake-judge")
    )
    trajectories = [
        _fake_traj("Q1", "Final answer: A"),
        _fake_traj("Q2", "Final answer: 120"),
        _fake_traj("Q3", "A valid-looking proof."),
    ]
    report = grade_exam(exam, trajectories, dummy, judge_fn=fake_judge)
    by_id = {q["question_id"]: q for q in report["questions"]}
    assert by_id["Q1"]["points_awarded"] == 4
    assert by_id["Q2"]["points_awarded"] == 6  # 4 numeric + 2 method
    assert by_id["Q3"]["points_awarded"] == 10
    assert report["points_awarded"] == 20
