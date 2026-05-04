# Logging and Feedback

## Goal

Each assistant turn produces exactly one JSONL row. The row captures everything needed to score the turn later: question, conversation context, what the agent retrieved (per tool call), the final answer, validation, and user feedback.

## Schema (extends existing `data/logs/queries.jsonl`)

```json
{
  "timestamp": "2026-05-04T12:00:00Z",
  "session_id": "uuid",
  "turn_index": 0,
  "question": "user message string",
  "conversation_history": [{"role": "user|assistant", "content": "..."}],
  "tool_calls": [
    {"query": "rewritten search string", "k": 5, "retrieved_chunk_ids": ["..."]}
  ],
  "retrieved_chunk_ids": ["union of all tool_calls' chunk_ids"],
  "retrieval_titles": ["..."],
  "generated_query": "PQL string",
  "explanation": "...",
  "cited_chunks": ["..."],
  "model": "gpt-4.1-mini",
  "validation_status": "passed|warned",
  "validation_warnings": ["..."],
  "user_feedback": null
}
```

Additive to current schema: `turn_index`, `conversation_history`, `tool_calls`, `explanation`. Existing readers stay compatible.

## Feedback write path

Two options, pick one in implementation:
- **In-place update:** each row gets a stable `row_id`; thumbs handler rewrites that row. Requires reading + rewriting the file. Fine at this volume.
- **Append delta:** thumbs writes a new row `{row_id, user_feedback}`; readers fold deltas. Cheaper writes, slightly more work to consume.

Recommend in-place for simplicity at v1 scale.

## Files touched

- `scripts/answer.py` — extend `_log_run` to include the new fields.
- New: `app/feedback.py` — write thumbs to the matching JSONL row.
