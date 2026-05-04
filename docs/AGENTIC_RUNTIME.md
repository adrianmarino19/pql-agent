# Agentic Runtime — `answer.py` refactor

## Why

Today `answer_question()` is a fixed linear pipeline: `retrieve → prompt → generate`. In a chat UI, follow-up turns like "make it case-insensitive" cannot be retrieved correctly from the latest message alone. Letting the LLM decide *whether and what* to retrieve handles short follow-ups, topic pivots, and "I have enough context already" turns uniformly.

## Shape

OpenAI tool-calling loop. The model is given one tool:

- `retrieve_pql_docs(query: string, k: integer = 5)` — wraps the existing `retrieve()` from `scripts/retrieve.py`. Returns the same `RetrievalResult` list, serialized.

Loop:

1. Build messages = system prompt + full chat history (user + assistant turns) + current user message.
2. Call the model with `tools=[retrieve_pql_docs]`.
3. If the response includes tool calls: execute each, append the tool result messages, loop. Cap at 3 retrievals per turn.
4. When the model returns a final assistant message, parse it as the existing JSON contract (`query`, `explanation`, `cited_chunks`).
5. Validate (existing `validate_answer`).
6. Log (see `LOGGING_AND_FEEDBACK.md`).

## System prompt changes

- Keep strict-grounding language.
- Add: "You may call `retrieve_pql_docs` zero or more times before answering. Call it whenever the user's request mentions PQL syntax, functions, or behaviors you are not already confident about from this conversation. Do not invent syntax."
- Keep the structured-output contract.

## Validation changes

`cited_chunks` should now be checked against the union of chunk IDs returned by *all* tool calls in the current turn (not a single retrieval). Update `validate_answer` to take that union.

## CLI parity

`main.py ask` keeps working. It runs a single-turn conversation through the same loop with an empty history.

## Files touched

- `scripts/answer.py` — main refactor.
- `scripts/retrieve.py` — no behavior change; expose a small adapter that produces JSON-serializable output for the tool result.
- `main.py` — adjust call site if signature changes.

## Risks

- **Cost/latency variance:** mitigate with the 3-retrieval cap and a per-call token budget.
- **Eval debuggability:** logs must capture each tool call (see logging doc).
