# Chat UI — Streamlit

## Layout

- Single page, `st.chat_input` at the bottom, message history above.
- 3–4 clickable example prompt chips above the input on cold start; clicking prefills the input.
- No sidebar for schema. Sidebar reserved for: model selector, top-k, "clear chat", session ID display (for cross-referencing logs).

## Message rendering

Each assistant message renders, in order:
1. `explanation` text.
2. `query` in `st.code(..., language="sql")` (closest highlighter; PQL is SQL-shaped enough). Streamlit's built-in copy button on code blocks satisfies the copy requirement.
3. Validation warnings, if any, as a yellow `st.warning` banner.
4. Expandable "Citations" section listing each `cited_chunk`: title, URL link, snippet preview.
5. Thumbs up / down buttons. Clicking writes feedback to that message's existing JSONL row (append-only style or in-place update — see logging doc).

## Session state

```python
st.session_state.session_id      # uuid4, stable for the browser session
st.session_state.messages        # list of {role, content, raw_answer?, log_row_id?}
st.session_state.message_count   # for soft throttle
```

## Soft throttle

If `message_count >= 20`, disable input and show "Session limit reached. Refresh to start a new session." The throttle is per-tab, not global; it's a deterrent against runaway loops, not abuse prevention.

## Example prompts

Seeded from the existing `main.py` examples and 2–3 representative ones from PQL docs:
- "Count cases where activity A happened before activity B."
- "Average throughput time per variant."
- "Filter cases that contain a rework loop."
- "Top 10 most frequent variants by case count."

## Files touched

- New: `app/streamlit_app.py` (entrypoint).
- New: `app/__init__.py`.
- `pyproject.toml` — add `streamlit` dependency.
- `README.md` — add "Run the UI: `uv run streamlit run app/streamlit_app.py`".
