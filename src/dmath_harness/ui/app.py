"""Streamlit UI for running and inspecting D-MATH harness trajectories.

Launch:
  PYTHONPATH=src pixi run streamlit run src/dmath_harness/ui/app.py
or:
  pixi run ui
"""

from __future__ import annotations

import json

import streamlit as st

from dmath_harness.agent import DEFAULT_STEP_LIMIT
from dmath_harness.exam import load_exam
from dmath_harness.ui.io_helpers import (
    MODEL_PRESETS,
    ROOT,
    find_matching_grades,
    grade_by_question,
    list_exam_paths,
    list_trajectory_paths,
    load_grade_report,
    load_trajectories,
    summarize_trajectories,
    write_trajectories,
)
from dmath_harness.ui.render import (
    render_conversation,
    render_grade_card,
    render_stats_row,
)
from dmath_harness.ui.runner import (
    default_out_path,
    grade_records,
    make_client,
    run_agent_questions,
    run_baseline_questions,
)
from dmath_harness.ui.theme import CUSTOM_CSS


def _init_state() -> None:
    defaults = {
        "records": [],
        "grade_report": None,
        "last_out_path": None,
        "source_label": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _question_label(q) -> str:
    return f"{q.id} · {q.type} · {q.topic} ({q.points:g} pts)"


def _apply_theme() -> None:
    st.markdown(f"<style>{CUSTOM_CSS}</style>", unsafe_allow_html=True)


def _sidebar() -> dict:
    st.sidebar.markdown("### Controls")

    exam_paths = list_exam_paths()
    if not exam_paths:
        st.sidebar.error(f"No exams found under `{ROOT / 'data' / 'exams'}`.")
        st.stop()

    exam_labels = {p.name: p for p in exam_paths}
    exam_name = st.sidebar.selectbox("Exam", list(exam_labels.keys()), index=0)
    exam_path = exam_labels[exam_name]
    exam = load_exam(exam_path)

    mode = st.sidebar.radio(
        "Harness",
        ["agent", "baseline"],
        format_func=lambda m: "ReAct agent (tools)" if m == "agent" else "Baseline (no tools)",
        horizontal=False,
    )

    preset_names = list(MODEL_PRESETS.keys()) + ["Custom"]
    preset = st.sidebar.selectbox("Model", preset_names, index=0)
    if preset == "Custom":
        model = st.sidebar.text_input("Model id", value="llama3.2:3b")
    else:
        model = MODEL_PRESETS[preset]
        st.sidebar.caption(model)

    q_options = {_question_label(q): q.id for q in exam.questions}
    default_labels = list(q_options.keys())
    selected_labels = st.sidebar.multiselect(
        "Questions",
        default_labels,
        default=default_labels,
    )
    question_ids = [q_options[label] for label in selected_labels]

    step_limit = DEFAULT_STEP_LIMIT
    if mode == "agent":
        step_limit = st.sidebar.number_input(
            "Step limit",
            min_value=1,
            max_value=32,
            value=DEFAULT_STEP_LIMIT,
            step=1,
        )

    grade_after = st.sidebar.checkbox("Grade after run", value=True)
    use_judge = st.sidebar.checkbox(
        "Use LLM judge",
        value=True,
        disabled=not grade_after,
        help="Needed for method points and proofs. Uncheck for deterministic-only.",
    )
    show_system = st.sidebar.checkbox("Show system prompt", value=False)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Load existing run")
    traj_paths = list_trajectory_paths(harness=mode)
    traj_choice = st.sidebar.selectbox(
        "Trajectory JSONL",
        ["—"] + [str(p.relative_to(ROOT)) for p in traj_paths],
        index=0,
    )
    load_clicked = st.sidebar.button("Load run", use_container_width=True)

    st.sidebar.markdown("---")
    run_clicked = st.sidebar.button("Run selected", type="primary", use_container_width=True)

    return {
        "exam": exam,
        "exam_path": exam_path,
        "mode": mode,
        "model": model.strip(),
        "question_ids": question_ids,
        "step_limit": int(step_limit),
        "grade_after": grade_after,
        "use_judge": use_judge,
        "show_system": show_system,
        "traj_choice": traj_choice,
        "load_clicked": load_clicked,
        "run_clicked": run_clicked,
    }


def _load_existing(ctrl: dict) -> None:
    if ctrl["traj_choice"] == "—":
        st.warning("Pick a trajectory file first.")
        return
    path = ROOT / ctrl["traj_choice"]
    records = load_trajectories(path)
    # Filter to selected questions if any are chosen
    if ctrl["question_ids"]:
        wanted = set(ctrl["question_ids"])
        filtered = [r for r in records if r.get("question_id") in wanted]
        if filtered:
            records = filtered
    grades_path = find_matching_grades(path)
    report = load_grade_report(grades_path)
    st.session_state.records = records
    st.session_state.grade_report = report
    st.session_state.last_out_path = str(path)
    st.session_state.source_label = f"Loaded `{path.relative_to(ROOT)}`"
    if grades_path:
        st.session_state.source_label += f" · grades `{grades_path.relative_to(ROOT)}`"


def _run_live(ctrl: dict) -> None:
    if not ctrl["question_ids"]:
        st.error("Select at least one question.")
        return
    if not ctrl["model"]:
        st.error("Model id is empty.")
        return

    status = st.status("Starting run…", expanded=True)

    def progress(msg: str) -> None:
        status.write(msg)

    try:
        progress(f"Connecting to model `{ctrl['model']}`…")
        client = make_client(ctrl["model"])
        if ctrl["mode"] == "agent":
            records = run_agent_questions(
                ctrl["exam"],
                ctrl["question_ids"],
                client,
                step_limit=ctrl["step_limit"],
                on_progress=progress,
            )
        else:
            records = run_baseline_questions(
                ctrl["exam"],
                ctrl["question_ids"],
                client,
                on_progress=progress,
            )

        out_path = default_out_path(ctrl["mode"], ctrl["model"], ctrl["exam"].exam_id)
        write_trajectories(records, out_path)
        progress(f"Wrote `{out_path.relative_to(ROOT)}`")

        report = None
        if ctrl["grade_after"]:
            report = grade_records(
                ctrl["exam"],
                records,
                use_judge=ctrl["use_judge"],
                on_progress=progress,
            )
            grade_path = out_path.with_name(f"grades_{out_path.stem}.json")
            grade_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            progress(f"Wrote `{grade_path.relative_to(ROOT)}`")

        st.session_state.records = records
        st.session_state.grade_report = report
        st.session_state.last_out_path = str(out_path)
        st.session_state.source_label = f"Live run → `{out_path.relative_to(ROOT)}`"
        status.update(label="Run finished", state="complete")
    except Exception as exc:  # noqa: BLE001 — surface any client/sandbox error in UI
        status.update(label="Run failed", state="error")
        st.error(f"{type(exc).__name__}: {exc}")


def _render_question_panel(
    record: dict,
    grade: dict | None,
    *,
    show_system: bool,
) -> None:
    qid = record.get("question_id", "?")
    topic = record.get("topic", "")
    difficulty = record.get("difficulty", "")
    points = record.get("points", "")
    qtype = record.get("question_type", "")

    st.markdown(
        f"**{qid}** · `{qtype}` · {topic} · {difficulty} · {points:g} pts"
        if isinstance(points, (int, float))
        else f"**{qid}** · `{qtype}` · {topic}"
    )

    usage = record.get("usage") or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tokens", f"{usage.get('total_tokens') or 0:,}")
    c2.metric("Latency", f"{record.get('latency_ms') or 0:,.0f} ms")
    c3.metric("Steps", record.get("step_count") or "—")
    finished = record.get("finished")
    c4.metric(
        "Finished",
        "yes" if finished is True else ("no" if finished is False else "—"),
    )

    tab_chat, tab_grade, tab_raw = st.tabs(["Conversation", "Grade", "Raw JSON"])
    with tab_chat:
        render_conversation(record.get("messages") or [], show_system=show_system)
        if record.get("assistant_text"):
            with st.expander("Final assistant_text", expanded=False):
                st.code(record["assistant_text"], language="markdown")
    with tab_grade:
        render_grade_card(grade)
    with tab_raw:
        st.json(record)


def main() -> None:
    st.set_page_config(
        page_title="D-MATH Harness",
        page_icon="∇",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _apply_theme()
    _init_state()

    st.markdown(
        """
        <div class="dmath-hero">
          <h1>D-MATH Harness</h1>
          <p>Run and inspect open-LLM baselines vs ReAct agents on ETH D-MATH exam items.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    ctrl = _sidebar()

    if ctrl["load_clicked"]:
        _load_existing(ctrl)
    if ctrl["run_clicked"]:
        _run_live(ctrl)

    records: list = st.session_state.records
    report = st.session_state.grade_report

    if st.session_state.source_label:
        st.caption(st.session_state.source_label)

    if not records:
        st.markdown(
            '<p class="dmath-muted">'
            "Select a model and questions in the sidebar, then press "
            "<strong>Run selected</strong> — or load an existing JSONL from "
            "<code>runs/</code>."
            "</p>",
            unsafe_allow_html=True,
        )
        return

    summary = summarize_trajectories(records)
    # For partial runs, recompute grade totals over present questions only
    display_report = report
    if report and records:
        present = {r.get("question_id") for r in records}
        q_grades = [
            q for q in report.get("questions", []) if q.get("question_id") in present
        ]
        if q_grades and len(q_grades) < len(report.get("questions", [])):
            awarded = sum(float(q.get("points_awarded") or 0) for q in q_grades)
            maximum = sum(float(q.get("max_points") or 0) for q in q_grades)
            pct = round(100.0 * awarded / maximum, 2) if maximum else 0.0
            display_report = {
                **report,
                "points_awarded": awarded,
                "total_points": maximum,
                "percent": pct,
                "questions": q_grades,
            }

    render_stats_row(summary, display_report)

    model = records[0].get("model", "—")
    harness = records[0].get("harness", ctrl["mode"])
    st.markdown(
        f'<p class="dmath-muted">model <code>{model}</code> · harness '
        f"<code>{harness}</code></p>",
        unsafe_allow_html=True,
    )

    grades = grade_by_question(display_report)
    for record in records:
        qid = record.get("question_id", "?")
        with st.expander(
            f"{qid} — {(record.get('assistant_text') or '')[:72] or '(empty)'}",
            expanded=len(records) == 1,
        ):
            _render_question_panel(
                record,
                grades.get(qid),
                show_system=ctrl["show_system"],
            )


if __name__ == "__main__":
    main()
