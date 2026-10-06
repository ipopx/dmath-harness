"""Deterministic answer extractors for MCQ and numeric finals."""

from __future__ import annotations

import re
from typing import Any


_FINAL_ANSWER_RE = re.compile(
    r"(?i)final\s*answer\s*[:\-]\s*(.+?)(?:\n|$)",
)
_MCQ_LETTER_RE = re.compile(r"\b([A-Za-z])\b")
_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+)(?:[eE][-+]?\d+)?")


def extract_mcq_letter(text: str, *, valid: set[str] | None = None) -> str | None:
    """Extract a multiple-choice letter from model output.

    Only reads a ``Final answer: X`` line. Exactly one valid letter → that
    letter; multiple letters or no Final-answer line → ``None``.
    """
    if not text or not text.strip():
        return None

    valid_norm = {v.upper() for v in valid} if valid else None

    match = _FINAL_ANSWER_RE.search(text)
    if match:
        letters = _letters_in_chunk(match.group(1), valid_norm)
        if len(letters) == 1:
            return letters[0]
        if len(letters) > 1:
            return None  # multi-letter final answer → not a single choice

    # Fallback disabled: only grade explicit Final answer lines.
    # found = _MCQ_LETTER_RE.findall(text)
    # for letter in reversed(found):
    #     upper = letter.upper()
    #     if valid_norm is None or upper in valid_norm:
    #         return upper
    return None


def _letters_in_chunk(chunk: str, valid: set[str] | None) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for letter in _MCQ_LETTER_RE.findall(chunk):
        upper = letter.upper()
        if valid is not None and upper not in valid:
            continue
        if upper not in seen:
            seen.add(upper)
            ordered.append(upper)
    return ordered


def extract_final_number(text: str) -> float | int | None:
    """Extract a numeric final answer.

    Only reads a ``Final answer: <n>`` line. Exactly one number → that value;
    multiple numbers or no Final-answer line → ``None``.
    """
    if not text or not text.strip():
        return None

    match = _FINAL_ANSWER_RE.search(text)
    if match:
        numbers = _numbers_in_chunk(match.group(1))
        if len(numbers) == 1:
            return numbers[0]
        if len(numbers) > 1:
            return None  # multi-number final answer → not a single value

    # Fallback disabled: only grade explicit Final answer lines.
    # numbers = _NUMBER_RE.findall(text)
    # if not numbers:
    #     return None
    # return _coerce_number(numbers[-1])
    return None


def numbers_equal(predicted: float | int | None, expected: Any, *, tol: float = 1e-6) -> bool:
    """Compare predicted numeric answer to exam reference."""
    if predicted is None or expected is None:
        return False
    try:
        exp = float(expected)
    except (TypeError, ValueError):
        return False
    return abs(float(predicted) - exp) <= tol


def _numbers_in_chunk(chunk: str) -> list[float | int]:
    """Return distinct numbers in order; strip thousand-separator commas first."""
    normalized = chunk
    # Turn 1,200 into 1200 so we don't split on thousands commas.
    while True:
        updated = re.sub(r"(\d),(\d{3})\b", r"\1\2", normalized)
        if updated == normalized:
            break
        normalized = updated

    ordered: list[float | int] = []
    seen: set[float] = set()
    for token in _NUMBER_RE.findall(normalized):
        value = _coerce_number(token)
        key = float(value)
        if key not in seen:
            seen.add(key)
            ordered.append(value)
    return ordered


def _coerce_number(token: str) -> float | int:
    value = float(token)
    if value.is_integer():
        return int(value)
    return value
