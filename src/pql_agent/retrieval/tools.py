from dataclasses import asdict
from typing import Any

from pql_agent.retrieval.retrieve import RetrievalResult, retrieve


def retrieval_result_to_dict(result: RetrievalResult) -> dict[str, Any]:
    return asdict(result)


def retrieve_pql_docs(query: str, k: int = 5) -> list[dict[str, Any]]:
    return [retrieval_result_to_dict(result) for result in retrieve(query, k=k)]
