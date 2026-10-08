"""HTML rendering for chat trajectories and grades."""

from __future__ import annotations

import html
import json
from typing import Any

import streamlit as st


def _esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def _pretty_args(raw: str | dict[str, Any] | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, dict):
        return json.dumps(raw, indent=2, ensure_ascii=False)
    try:
        parsed = json.loads(raw)
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    except (TypeError, json.JSONDecodeError):
        return str(raw)


def render_message(msg: dict[str, Any], *, show_system: bool = False) -> None:
    role = msg.get("role") or "unknown"
    if role == "system" and not show_system:
        return

    content = msg.get("content")
    if content is None:
        content = ""
    elif not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)

    tool_calls = msg.get("tool_calls") or []
    role_label = {
        "system": "System",
        "user": "Question",
        "assistant": "Assistant",
        "tool": "Tool result",
    }.get(role, role.title())

    extra = ""
    if role == "tool" and msg.get("tool_call_id"):
        extra = f" · {_esc(str(msg['tool_call_id']))}"

    tool_html = ""
    for tc in tool_calls:
        fn = tc.get("function") or {}
        name = fn.get("name") or tc.get("name") or "tool"
        args = _pretty_args(fn.get("arguments") if "function" in tc else tc.get("arguments"))
        tool_html += (
            f'<div class="dmath-tool-call">'
            f'<div class="dmath-tool-name">⚙ { _esc(name) }</div>'
            f"<pre style='margin:0; white-space:pre-wrap;'>{_esc(args)}</pre>"
            f"</div>"
        )

    body = _esc(content) if content.strip() else (
        "<span class='dmath-muted'>(no text — tool call only)</span>" if tool_calls else ""
    )

    st.markdown(
        f'<div class="dmath-msg dmath-msg-{_esc(role)}">'
        f'<div class="dmath-msg-role">{_esc(role_label)}{extra}</div>'
        f'<div class="dmath-msg-body">{body}</div>'
        f"{tool_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_conversation(
    messages: list[dict[str, Any]],
    *,
    show_system: bool = False,
) -> None:
    for msg in messages:
        render_message(msg, show_system=show_system)


def render_grade_card(grade: dict[str, Any] | None) -> None:
    if not grade:
        st.markdown(
            '<p class="dmath-muted">No grade for this question yet.</p>',
            unsafe_allow_html=True,
        )
        return

    awarded = grade.get("points_awarded")
    maximum = grade.get("max_points")
    predicted = grade.get("predicted")
    expected = grade.get("expected")
    rationale = grade.get("rationale") or ""
    method = grade.get("grading") or ""

    ok = awarded is not None and maximum is not None and float(awarded) >= float(maximum) > 0
    badge_cls = "dmath-badge-ok" if ok else "dmath-badge-warn"
    badge = "full credit" if ok else "partial / miss"

    pred_line = ""
    if predicted is not None or expected is not None:
        pred_line = (
            f"<p class='dmath-muted' style='margin:0.35rem 0 0 0;'>"
            f"Predicted <code>{_esc(str(predicted))}</code> · "
            f"Expected <code>{_esc(str(expected))}</code></p>"
        )

    st.markdown(
        f'<div class="dmath-grade-box">'
        f'<span class="dmath-badge {badge_cls}">{badge}</span>'
        f'<span class="dmath-badge dmath-badge-info">{_esc(method)}</span>'
        f'<div class="dmath-grade-score" style="margin-top:0.55rem;">'
        f"{_esc(str(awarded))} / {_esc(str(maximum))} pts"
        f"</div>"
        f"{pred_line}"
        f"<p style='margin:0.55rem 0 0 0; line-height:1.5;'>{_esc(rationale)}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_stats_row(
    summary: dict[str, Any],
    report: dict[str, Any] | None = None,
) -> None:
    cols = st.columns(5)
    cols[0].metric("Questions", summary.get("n_questions", 0))
    cols[1].metric("Tokens", f"{summary.get('total_tokens', 0):,}")
    cols[2].metric("Latency", f"{summary.get('latency_ms', 0):,.0f} ms")
    cols[3].metric("Steps", summary.get("step_count", 0))
    if report:
        pts = report.get("points_awarded")
        total = report.get("total_points")
        pct = report.get("percent")
        cols[4].metric("Grade", f"{pts}/{total} ({pct}%)")
    else:
        cols[4].metric("Grade", "—")
