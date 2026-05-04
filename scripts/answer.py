import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from openai import OpenAI

from retrieve import RetrievalResult, retrieve

DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_K = 5
DEFAULT_LOG_PATH = Path("data/logs/queries.jsonl")


@dataclass
class Answer:
    query: str
    explanation: str
    cited_chunks: list[str]


@dataclass
class ValidationResult:
    status: str
    warnings: list[str]


def _chunk_context(results: list[RetrievalResult]) -> str:
    blocks = []
    for index, result in enumerate(results, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[{index}] chunk_id: {result.chunk_id}",
                    f"title: {result.title}",
                    f"term_name: {result.term_name or '-'}",
                    f"chunk_type: {result.chunk_type}",
                    f"url: {result.url}",
                    "content:",
                    result.text,
                ]
            )
        )
    return "\n\n---\n\n".join(blocks)


def build_prompt(question: str, results: list[RetrievalResult], schema: str | None = None) -> list[dict[str, str]]:
    schema_block = schema.strip() if schema and schema.strip() else "No schema context was provided."
    valid_chunk_ids = [result.chunk_id for result in results]
    user_content = f"""User request:
{question}

Schema context:
{schema_block}

Valid chunk IDs:
{json.dumps(valid_chunk_ids)}

Retrieved documentation chunks:
{_chunk_context(results)}

Return JSON only with exactly these keys:
- query: string
- explanation: string
- cited_chunks: array containing only strings from the Valid chunk IDs list above
"""

    return [
        {
            "role": "system",
            "content": (
                "You are a PQL authoring assistant. Use only the retrieved Celonis PQL "
                "documentation chunks as the source of truth for PQL syntax and functions. "
                "Do not invent PQL functions, arguments, or syntax. If the request cannot be "
                "answered from the retrieved documentation or provided schema, put the needed "
                "clarification in the explanation and leave query as an empty string. Cite only "
                "chunk IDs that appear in the Valid chunk IDs list. Bracketed example numbers "
                "such as [1] or [4] are not chunk IDs."
            ),
        },
        {"role": "user", "content": user_content},
    ]


def _parse_answer(content: str) -> Answer:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model returned invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Model response must be a JSON object.")

    allowed_keys = {"query", "explanation", "cited_chunks"}
    extra_keys = set(payload) - allowed_keys
    if extra_keys:
        raise ValueError(f"Model response contained unsupported keys: {sorted(extra_keys)}")

    query = payload.get("query")
    explanation = payload.get("explanation")
    cited_chunks = payload.get("cited_chunks")

    if not isinstance(query, str):
        raise ValueError("Model response field 'query' must be a string.")
    if not isinstance(explanation, str):
        raise ValueError("Model response field 'explanation' must be a string.")
    if not isinstance(cited_chunks, list) or not all(isinstance(item, str) for item in cited_chunks):
        raise ValueError("Model response field 'cited_chunks' must be an array of strings.")

    return Answer(query=query.strip(), explanation=explanation.strip(), cited_chunks=cited_chunks)


def generate_answer(
    question: str,
    results: list[RetrievalResult],
    schema: str | None = None,
    model: str = DEFAULT_MODEL,
) -> Answer:
    load_dotenv()
    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        messages=build_prompt(question, results, schema=schema),
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Model returned an empty response.")
    return _parse_answer(content)


def _called_pql_terms(query: str) -> set[str]:
    return set(re.findall(r"\b([A-Z][A-Z0-9_]{2,})\s*\(", query))


def validate_answer(answer: Answer, results: list[RetrievalResult]) -> ValidationResult:
    warnings = []
    retrieved_ids = {result.chunk_id for result in results}
    cited_ids = set(answer.cited_chunks)

    unknown_citations = sorted(cited_ids - retrieved_ids)
    if unknown_citations:
        warnings.append(f"cited_chunks contains IDs that were not retrieved: {unknown_citations}")

    if answer.query and not answer.cited_chunks:
        warnings.append("query is non-empty but cited_chunks is empty")

    if not answer.query and not answer.explanation:
        warnings.append("query and explanation are both empty")

    if re.search(r"(<[^>]+>|\bTODO\b|\?\?\?)", answer.query, flags=re.IGNORECASE):
        warnings.append("query appears to contain unresolved placeholders")

    retrieved_terms = {result.term_name for result in results if result.term_name}
    called_terms = _called_pql_terms(answer.query)
    uncited_terms = sorted(term for term in called_terms if term not in retrieved_terms)
    if uncited_terms:
        warnings.append(f"query references PQL calls not represented by retrieved term metadata: {uncited_terms}")

    return ValidationResult(status="warned" if warnings else "passed", warnings=warnings)


def _read_schema(schema: str | None, schema_file: str | None) -> str | None:
    parts = []
    if schema:
        parts.append(schema)
    if schema_file:
        parts.append(Path(schema_file).read_text())
    if not parts:
        return None
    return "\n\n".join(part.strip() for part in parts if part.strip())


def _log_run(
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


def answer_question(
    question: str,
    *,
    schema: str | None = None,
    model: str = DEFAULT_MODEL,
    top_k: int = DEFAULT_K,
    log_path: Path | None = DEFAULT_LOG_PATH,
    session_id: str | None = None,
) -> dict[str, Any]:
    session_id = session_id or str(uuid4())
    results = retrieve(question, k=top_k)
    answer = generate_answer(question, results, schema=schema, model=model)
    validation = validate_answer(answer, results)

    if log_path is not None:
        _log_run(log_path, session_id, question, results, answer, validation, model)

    return {
        **asdict(answer),
        "session_id": session_id,
        "validation": asdict(validation),
        "retrieved_chunks": [
            {
                "chunk_id": result.chunk_id,
                "title": result.title,
                "term_name": result.term_name,
                "chunk_type": result.chunk_type,
                "url": result.url,
                "similarity": result.similarity,
                "boosted_similarity": result.boosted_similarity,
            }
            for result in results
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a grounded PQL answer.")
    parser.add_argument("question", help="Natural-language PQL request.")
    parser.add_argument("-k", "--top-k", type=int, default=DEFAULT_K, help="Number of chunks to retrieve.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI chat model to use.")
    parser.add_argument("--schema", help="Inline table/column schema context.")
    parser.add_argument("--schema-file", help="Path to a file containing table/column schema context.")
    parser.add_argument("--session-id", help="Optional session ID to store in the query log.")
    parser.add_argument(
        "--log-path",
        default=str(DEFAULT_LOG_PATH),
        help="JSONL log path. Use an empty string to disable logging.",
    )
    args = parser.parse_args(argv)

    try:
        schema = _read_schema(args.schema, args.schema_file)
        output = answer_question(
            args.question,
            schema=schema,
            model=args.model,
            top_k=args.top_k,
            log_path=Path(args.log_path) if args.log_path else None,
            session_id=args.session_id,
        )
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
