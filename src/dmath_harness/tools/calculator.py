"""Safe arithmetic calculator tool (restricted AST evaluation)."""

from __future__ import annotations

import ast
import operator
from typing import Any


CALCULATOR_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "calculator",
        "description": (
            "Evaluate a pure arithmetic expression. Supports +, -, *, /, //, %, **, "
            "unary +/- , numbers, and parentheses. No variables or function calls."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Arithmetic expression to evaluate, e.g. '(10*9*8)/(3*2*1)'.",
                },
            },
            "required": ["expression"],
        },
    },
}

_BINARY_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS: dict[type, Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_node(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value!r}")

    # Python <3.8 compatibility not needed (we require 3.11+), but Num keeps tests clear.
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op(_eval_node(node.operand))

    if isinstance(node, ast.BinOp):
        op = _BINARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return op(left, right)

    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def evaluate_expression(expression: str) -> str:
    """Evaluate a safe arithmetic expression; return result or error string."""
    expr = expression.strip()
    if not expr:
        return "Error: empty expression"

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        return f"Error: invalid expression syntax: {exc.msg}"

    try:
        value = _eval_node(tree)
    except ZeroDivisionError:
        return "Error: division by zero"
    except (ValueError, TypeError, OverflowError) as exc:
        return f"Error: {exc}"

    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def run_calculator(arguments: dict[str, Any]) -> str:
    expression = arguments.get("expression")
    if not isinstance(expression, str):
        return "Error: 'expression' must be a string"
    return evaluate_expression(expression)
