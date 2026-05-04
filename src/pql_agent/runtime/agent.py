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
from pql_agent.retrieval.retrieve import RetrievalResult
from pql_agent.retrieval.tools import retrieve_pql_docs
from pql_agent.runtime.logging import log_run
from pql_agent.runtime.models import Answer, ToolCallTrace
from pql_agent.runtime.validation import validate_answer

MAX_RETRIEVALS_PER_TURN = 3

SYSTEM_PROMPT = """You are a PQL authoring assistant. Use only retrieved Celonis PQL documentation chunks and provided schema context as the source of truth for PQL syntax and functions.

You may call retrieve_pql_docs zero or more times before answering. Call it whenever the user's request mentions PQL syntax, functions, or behaviors you are not already confident about from this conversation. Do not invent PQL functions, arguments, or syntax.

If the request cannot be answered from retrieved documentation, conversation context, or provided schema, put the needed clarification in the explanation and leave query as an empty string. Cite only chunk IDs returned by retrieve_pql_docs in the current turn. Bracketed example numbers such as [1] or [4] are not chunk IDs.

Return JSON only with exactly these keys:
- query: string
- explanation: string
- cited_chunks: array of strings
"""

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "query": {"type": "string"},
        "explanation": {"type": "string"},
        "cited_chunks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["query", "explanation", "cited_chunks"],
}

RETRIEVE_PQL_DOCS_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "retrieve_pql_docs",
    "description": (
        "Retrieve relevant Celonis PQL documentation chunks for syntax, "
        "function behavior, arguments, and examples."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "query": {
                "type": "string",
                "description": "Focused search query for the PQL documentation.",
            },
            "k": {
                "type": "integer",
                "description": "Number of documentation chunks to retrieve.",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
    },
    "strict": False,
}


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


def _build_current_user_message(question: str, schema: str | None) -> str:
    schema_block = schema.strip() if schema and schema.strip() else "No schema context was provided."
    return f"""User request:
{question}

Schema context:
{schema_block}
"""


def _normalize_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    normalized = []
    for message in history or []:
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"}:
            raise ValueError("history messages must use role 'user' or 'assistant'.")
        if not isinstance(content, str):
            raise ValueError("history message content must be a string.")
        normalized.append({"role": role, "content": content})
    return normalized


def _parse_tool_arguments(raw_arguments: str, default_k: int) -> tuple[str, int]:
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model called retrieve_pql_docs with invalid JSON arguments: {exc}") from exc

    if not isinstance(arguments, dict):
        raise ValueError("Model called retrieve_pql_docs with non-object arguments.")

    query = arguments.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Model called retrieve_pql_docs without a non-empty query string.")

    raw_k = arguments.get("k", default_k)
    if not isinstance(raw_k, int):
        raise ValueError("Model called retrieve_pql_docs with non-integer k.")

    return query.strip(), max(1, min(raw_k, 10))


def _dict_to_retrieval_result(payload: dict[str, Any]) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=str(payload.get("chunk_id") or ""),
        title=str(payload.get("title") or ""),
        term_name=str(payload.get("term_name") or ""),
        chunk_type=str(payload.get("chunk_type") or ""),
        url=str(payload.get("url") or ""),
        text=str(payload.get("text") or ""),
        distance=float(payload.get("distance") or 0),
        similarity=float(payload.get("similarity") or 0),
        boosted_similarity=float(payload.get("boosted_similarity") or 0),
        term_match=bool(payload.get("term_match")),
    )


def _merge_retrieval_results(tool_calls: list[ToolCallTrace]) -> list[RetrievalResult]:
    by_id: dict[str, RetrievalResult] = {}
    for tool_call in tool_calls:
        for result_payload in tool_call.results:
            result = _dict_to_retrieval_result(result_payload)
            if result.chunk_id and result.chunk_id not in by_id:
                by_id[result.chunk_id] = result
    return list(by_id.values())


def _tool_call_trace_for_output(tool_call: ToolCallTrace) -> dict[str, Any]:
    return {
        "tool_name": tool_call.tool_name,
        "query": tool_call.query,
        "k": tool_call.k,
        "retrieved_chunk_ids": tool_call.retrieved_chunk_ids,
        "retrieval_titles": [str(result.get("title") or "") for result in tool_call.results],
    }


def _output_function_calls(response: Any) -> list[Any]:
    return [item for item in response.output if item.type == "function_call"]


def run_agentic_loop(
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
    schema: str | None = None,
    model: str = DEFAULT_MODEL,
    top_k: int = DEFAULT_K,
    max_retrievals: int = MAX_RETRIEVALS_PER_TURN,
) -> tuple[Answer, list[ToolCallTrace]]:
    load_dotenv()
    client = OpenAI()
    normalized_history = _normalize_history(history)
    input_messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *normalized_history,
        {"role": "user", "content": _build_current_user_message(question, schema)},
    ]

    previous_response_id: str | None = None
    tool_calls: list[ToolCallTrace] = []
    next_input: list[dict[str, Any]] | list[dict[str, str]] = input_messages

    iterations = 0
    while True:
        iterations += 1
        if iterations > max_retrievals + 2:
            raise ValueError("Agentic loop did not produce a final answer within the retrieval cap.")

        response_kwargs: dict[str, Any] = {
            "model": model,
            "input": next_input,
            "tools": [RETRIEVE_PQL_DOCS_TOOL],
            "parallel_tool_calls": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "pql_answer",
                    "schema": ANSWER_SCHEMA,
                    "strict": True,
                }
            },
        }
        if previous_response_id is not None:
            response_kwargs["previous_response_id"] = previous_response_id

        response = client.responses.create(**response_kwargs)

        function_calls = _output_function_calls(response)
        if not function_calls:
            content = response.output_text
            if not content:
                raise ValueError("Model returned an empty response.")
            return _parse_answer(content), tool_calls

        previous_response_id = response.id
        next_outputs: list[dict[str, Any]] = []
        for function_call in function_calls:
            if function_call.name != "retrieve_pql_docs":
                next_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": function_call.call_id,
                        "output": json.dumps({"error": f"Unsupported tool: {function_call.name}"}),
                    }
                )
                continue

            if len(tool_calls) >= max_retrievals:
                next_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": function_call.call_id,
                        "output": json.dumps(
                            {"error": f"Retrieval cap exceeded. Max {max_retrievals} calls per turn."}
                        ),
                    }
                )
                continue

            query, k = _parse_tool_arguments(function_call.arguments, top_k)
            results = retrieve_pql_docs(query, k=k)
            trace = ToolCallTrace(
                tool_name="retrieve_pql_docs",
                query=query,
                k=k,
                retrieved_chunk_ids=[str(result.get("chunk_id") or "") for result in results],
                results=results,
            )
            tool_calls.append(trace)
            next_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": function_call.call_id,
                    "output": json.dumps(results),
                }
            )

        next_input = next_outputs


def answer_question(
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
    schema: str | None = None,
    model: str = DEFAULT_MODEL,
    top_k: int = DEFAULT_K,
    log_path: Path | None = DEFAULT_LOG_PATH,
    session_id: str | None = None,
    turn_index: int | None = None,
) -> dict[str, Any]:
    session_id = session_id or str(uuid4())
    normalized_history = _normalize_history(history)
    resolved_turn_index = (
        turn_index if turn_index is not None else sum(1 for message in normalized_history if message["role"] == "user")
    )
    answer, tool_calls = run_agentic_loop(
        question,
        history=normalized_history,
        schema=schema,
        model=model,
        top_k=top_k,
    )
    results = _merge_retrieval_results(tool_calls)
    validation = validate_answer(answer, results)
    log_row_id = None

    if log_path is not None:
        log_row_id = log_run(
            log_path,
            session_id,
            question,
            results,
            answer,
            validation,
            model,
            turn_index=resolved_turn_index,
            conversation_history=normalized_history,
            tool_calls=[_tool_call_trace_for_output(tool_call) for tool_call in tool_calls],
        )

    return {
        **asdict(answer),
        "session_id": session_id,
        "turn_index": resolved_turn_index,
        "log_row_id": log_row_id,
        "validation": asdict(validation),
        "tool_calls": [_tool_call_trace_for_output(tool_call) for tool_call in tool_calls],
        "retrieved_chunks": [
            {
                "chunk_id": result.chunk_id,
                "title": result.title,
                "term_name": result.term_name,
                "chunk_type": result.chunk_type,
                "url": result.url,
                "text": result.text,
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
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model to use.")
    parser.add_argument("--schema", help="Inline table/column schema context.")
    parser.add_argument("--schema-file", help="Path to a file containing table/column schema context.")
    parser.add_argument("--session-id", help="Optional session ID to store in the query log.")
    parser.add_argument("--turn-index", type=int, help="Optional turn index to store in the query log.")
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
            turn_index=args.turn_index,
        )
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(output, indent=2))
    return 0
