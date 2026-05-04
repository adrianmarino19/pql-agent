from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from app.feedback import write_feedback
from pql_agent.config import DEFAULT_K, DEFAULT_LOG_PATH, DEFAULT_MODEL
from pql_agent.runtime.agent import answer_question

SESSION_LIMIT = 20
EXAMPLE_PROMPTS = [
    "Count cases where activity A happened before activity B.",
    "Average throughput time per variant.",
    "Filter cases that contain a rework loop.",
    "Top 10 most frequent variants by case count.",
]
MODEL_OPTIONS = [DEFAULT_MODEL, "gpt-4.1", "gpt-4.1-nano"]


def _configure_openai_key() -> None:
    if os.getenv("OPENAI_API_KEY"):
        return
    try:
        secret_key = st.secrets.get("OPENAI_API_KEY")
    except (FileNotFoundError, KeyError, StreamlitSecretNotFoundError):
        secret_key = None
    if secret_key:
        os.environ["OPENAI_API_KEY"] = str(secret_key)


def _init_state() -> None:
    st.session_state.setdefault("session_id", str(uuid4()))
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("message_count", 0)


def _assistant_history_content(answer: dict) -> str:
    return json.dumps(
        {
            "query": answer.get("query", ""),
            "explanation": answer.get("explanation", ""),
            "cited_chunks": answer.get("cited_chunks", []),
        }
    )


def _history_for_runtime() -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in st.session_state.messages:
        if message["role"] == "user":
            history.append({"role": "user", "content": message["content"]})
        elif message["role"] == "assistant":
            history.append({"role": "assistant", "content": _assistant_history_content(message["answer"])})
    return history


def _citation_lookup(answer: dict) -> dict[str, dict]:
    return {chunk.get("chunk_id", ""): chunk for chunk in answer.get("retrieved_chunks", [])}


def _render_citations(answer: dict) -> None:
    cited_chunks = answer.get("cited_chunks", [])
    if not cited_chunks:
        return

    chunks_by_id = _citation_lookup(answer)
    with st.expander("Citations"):
        for chunk_id in cited_chunks:
            chunk = chunks_by_id.get(chunk_id, {"chunk_id": chunk_id})
            title = chunk.get("title") or chunk.get("term_name") or chunk_id
            url = chunk.get("url") or ""
            text = (chunk.get("text") or "").strip()
            preview = text[:450] + ("..." if len(text) > 450 else "")

            if url:
                st.markdown(f"**[{title}]({url})**")
            else:
                st.markdown(f"**{title}**")
            st.caption(chunk_id)
            if preview:
                st.write(preview)


def _render_feedback(message_index: int, answer: dict) -> None:
    row_id = answer.get("log_row_id")
    if not row_id:
        return

    current_feedback = answer.get("user_feedback")
    cols = st.columns([0.08, 0.08, 0.84])
    for label, value, column in [("Thumbs up", "up", cols[0]), ("Thumbs down", "down", cols[1])]:
        button_label = "+1" if value == "up" else "-1"
        if column.button(button_label, key=f"feedback-{message_index}-{value}", help=label):
            if write_feedback(ROOT / DEFAULT_LOG_PATH, row_id, value):
                answer["user_feedback"] = value
                st.session_state.messages[message_index]["answer"] = answer
                st.rerun()
    if current_feedback:
        cols[2].caption(f"Feedback recorded: {current_feedback}")


def _render_assistant_message(message_index: int, answer: dict) -> None:
    if answer.get("explanation"):
        st.write(answer["explanation"])
    if answer.get("query"):
        st.code(answer["query"], language="sql")

    validation = answer.get("validation") or {}
    warnings = validation.get("warnings") or []
    if warnings:
        st.warning("\n".join(warnings))

    _render_citations(answer)
    _render_feedback(message_index, answer)


def _render_message(message_index: int, message: dict) -> None:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.write(message["content"])
        else:
            _render_assistant_message(message_index, message["answer"])


def _submit_prompt(prompt: str, model: str, top_k: int) -> None:
    history = _history_for_runtime()
    turn_index = sum(1 for message in st.session_state.messages if message["role"] == "user")
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Generating grounded PQL..."):
            answer = answer_question(
                prompt,
                history=history,
                model=model,
                top_k=top_k,
                session_id=st.session_state.session_id,
                turn_index=turn_index,
                log_path=ROOT / DEFAULT_LOG_PATH,
            )
        st.session_state.messages.append({"role": "assistant", "answer": answer})
        st.session_state.message_count += 1
        _render_assistant_message(len(st.session_state.messages) - 1, answer)


def main() -> None:
    st.set_page_config(page_title="PQL Agent", layout="centered")
    _configure_openai_key()
    _init_state()

    with st.sidebar:
        model = st.selectbox("Model", MODEL_OPTIONS, index=0)
        top_k = st.slider("Top-k", min_value=1, max_value=10, value=DEFAULT_K)
        st.text_input("Session ID", value=st.session_state.session_id, disabled=True)
        if st.button("Clear chat", use_container_width=True):
            st.session_state.session_id = str(uuid4())
            st.session_state.messages = []
            st.session_state.message_count = 0
            st.rerun()

    st.title("PQL Agent")

    for index, message in enumerate(st.session_state.messages):
        _render_message(index, message)

    if not st.session_state.messages:
        cols = st.columns(2)
        for index, prompt in enumerate(EXAMPLE_PROMPTS):
            if cols[index % 2].button(prompt, key=f"example-{index}", use_container_width=True):
                _submit_prompt(prompt, model, top_k)
                st.rerun()

    if st.session_state.message_count >= SESSION_LIMIT:
        st.info("Session limit reached. Refresh to start a new session.")
        st.chat_input("Ask for PQL", disabled=True)
        return

    prompt = st.chat_input("Ask for PQL")
    if prompt:
        _submit_prompt(prompt, model, top_k)
        st.rerun()


if __name__ == "__main__":
    main()
