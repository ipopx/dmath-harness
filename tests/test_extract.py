from dmath_harness.judge import extract_final_number, extract_mcq_letter, numbers_equal


def test_extract_mcq_prefers_final_answer():
    text = "I think B is wrong.\nFinal answer: A\n"
    assert extract_mcq_letter(text, valid={"A", "B", "C", "D"}) == "A"


def test_extract_mcq_rejects_multi_letter_final():
    text = "Therefore A, B, and C are tautologies.\nFinal answer: A, B, C"
    assert extract_mcq_letter(text, valid={"A", "B", "C", "D"}) is None


def test_extract_mcq_no_fallback_without_final_answer():
    text = "Option C looks good. Wait, actually B."
    assert extract_mcq_letter(text, valid={"A", "B", "C", "D"}) is None


def test_extract_mcq_respects_valid_set():
    text = "Final answer: Z"
    assert extract_mcq_letter(text, valid={"A", "B", "C", "D"}) is None


def test_extract_final_number_from_tag():
    text = "We get C(10,3)=120.\nFinal answer: 120\n"
    assert extract_final_number(text) == 120


def test_extract_final_number_rejects_multi_number_final():
    text = "Could be 120 or 240.\nFinal answer: 120, 240"
    assert extract_final_number(text) is None


def test_extract_final_number_allows_thousands_comma():
    text = "Final answer: 1,200"
    assert extract_final_number(text) == 1200


def test_extract_final_number_no_fallback_without_final_answer():
    text = "First 10 then 3 then 120."
    assert extract_final_number(text) is None


def test_numbers_equal():
    assert numbers_equal(120, 120)
    assert numbers_equal(120.0, "120")
    assert not numbers_equal(119, 120)
    assert not numbers_equal(None, 120)
