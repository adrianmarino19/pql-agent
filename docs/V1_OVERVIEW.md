# v1 Frontend — Overview

## Purpose

Evaluation-first. Every interaction with a Celonis employee should yield a labeled row in `data/logs/queries.jsonl` so we can find where the agent is wrong. Demo polish is a secondary constraint.

## Scope (resolved decisions)

- **Interaction:** multi-turn chat, ChatGPT/Claude-style.
- **Output rendering:** `query` in a syntax-highlighted code block with copy button; `explanation` as text; citations as expandable cards; validation warnings as a yellow banner when present.
- **Schema input:** none. Users inline schema context in the prompt itself.
- **Retrieval:** agentic — the LLM decides per turn whether to call the `retrieve_pql_docs` tool (0–3 times per turn).
- **Feedback:** thumbs up / down per assistant message, written to that message's JSONL row.
- **Cold start:** empty chat + 3–4 clickable example prompt chips.
- **Deployment:** Streamlit Community Cloud, repo-backed, `data/chroma/` committed.
- **API key:** project owner's `OPENAI_API_KEY` in Streamlit secrets, soft-throttle ~20 messages per session.

## Build order

1. Agentic runtime refactor — see `AGENTIC_RUNTIME.md`.
2. Logging schema extension — see `LOGGING_AND_FEEDBACK.md`.
3. Streamlit chat UI — see `CHAT_UI.md`.
4. Deployment to Streamlit Cloud — see `DEPLOYMENT.md`.
5. Idempotent pipeline re-run (follow-up, quality of life) — see `ITERATION_WORKFLOW.md`.

## What is explicitly out of scope for v1

- Multi-user auth.
- Server-side persistence beyond the JSONL log.
- Automated eval harness (logs feed manual review for now).
- Hybrid dense+keyword search beyond what `retrieve.py` already does.
- Fine-tuning.
