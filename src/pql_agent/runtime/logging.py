import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pql_agent.retrieval.retrieve import RetrievalResult
from pql_agent.runtime.models import Answer, ValidationResult


def log_run(
    path: Path,
    session_id: str,
    question: str,
    results: list[RetrievalResult],
    answer: Answer,
    validation: ValidationResult,
    model: str,
    *,
    turn_index: int | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "session_id": session_id,
        "turn_index": turn_index,
        "question": question,
        "conversation_history": conversation_history or [],
        "tool_calls": tool_calls or [],
        "retrieved_chunk_ids": [result.chunk_id for result in results],
        "retrieval_titles": [result.title for result in results],
        "generated_query": answer.query,
        "explanation": answer.explanation,
        "cited_chunks": answer.cited_chunks,
        "model": model,
        "validation_status": validation.status,
        "validation_warnings": validation.warnings,
        "user_feedback": None,
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")
