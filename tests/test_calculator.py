"""Tests for the safe calculator tool and dispatcher."""

from dmath_harness.tools.calculator import evaluate_expression, run_calculator
from dmath_harness.tools.dispatch import dispatch_tool_call


def test_evaluate_basic_arithmetic():
    assert evaluate_expression("1 + 2 * 3") == "7"
    assert evaluate_expression("(10 * 9 * 8) / (3 * 2 * 1)") == "120"
    assert evaluate_expression("2 ** 10") == "1024"
    assert evaluate_expression("-5 + 3") == "-2"
    assert evaluate_expression("7 // 2") == "3"
    assert evaluate_expression("7 % 2") == "1"


def test_evaluate_rejects_unsafe():
    assert evaluate_expression("__import__('os')").startswith("Error:")
    assert evaluate_expression("abs(1)").startswith("Error:")
    assert evaluate_expression("x + 1").startswith("Error:")
    assert evaluate_expression("").startswith("Error:")


def test_division_by_zero():
    assert evaluate_expression("1 / 0") == "Error: division by zero"


def test_run_calculator_and_dispatch():
    assert run_calculator({"expression": "2+2"}) == "4"
    assert run_calculator({"expression": 123}).startswith("Error:")
    assert dispatch_tool_call("calculator", '{"expression": "3*4"}') == "12"
    assert dispatch_tool_call("calculator", "not-json").startswith("Error:")
    assert dispatch_tool_call("unknown_tool", "{}").startswith("Error:")
