import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from openai import OpenAI

from pql_agent.config import DEFAULT_K, DEFAULT_LOG_PATH, DEFAULT_MODEL
from pql_agent.retrieval.retrieve import RetrievalResult, retrieve
from pql_agent.runtime.logging import log_run
from pql_agent.runtime.models import Answer
from pql_agent.runtime.prompts import build_prompt
from pql_agent.runtime.validation import validate_answer


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
        log_run(log_path, session_id, question, results, answer, validation, model)

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


def _read_schema(schema: str | None, schema_file: str | None) -> str | None:
    parts = []
    if schema:
        parts.append(schema)
    if schema_file:
        parts.append(Path(schema_file).read_text())
    if not parts:
        return None
    return "\n\n".join(part.strip() for part in parts if part.strip())


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

