import json

from pql_agent.retrieval.retrieve import RetrievalResult


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

