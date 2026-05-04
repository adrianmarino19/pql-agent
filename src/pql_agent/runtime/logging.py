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
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "session_id": session_id,
        "question": question,
        "retrieved_chunk_ids": [result.chunk_id for result in results],
        "retrieval_titles": [result.title for result in results],
        "generated_query": answer.query,
        "cited_chunks": answer.cited_chunks,
        "model": model,
        "validation_status": validation.status,
        "validation_warnings": validation.warnings,
        "user_feedback": None,
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")

