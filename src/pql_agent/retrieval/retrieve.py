import argparse
import re
import sys
from dataclasses import dataclass
from typing import Any

from pql_agent.config import DEFAULT_K
from pql_agent.retrieval.chroma import collection as get_collection
from pql_agent.retrieval.embeddings import embed_query

DEFAULT_MAX_CHARS = 800
TERM_BOOST = 0.15


@dataclass
class RetrievalResult:
    chunk_id: str
    title: str
    term_name: str
    chunk_type: str
    url: str
    text: str
    distance: float
    similarity: float
    boosted_similarity: float
    term_match: bool


def _query_terms(collection) -> set[str]:
    data = collection.get(include=["metadatas"])
    terms: set[str] = set()
    for metadata in data.get("metadatas") or []:
        term = (metadata or {}).get("term_name")
        if term:
            terms.add(str(term))
    return terms


def _contains_term(query: str, term: str) -> bool:
    normalized_query = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    term_forms = {
        re.sub(r"[^a-z0-9]+", " ", term.lower()).strip(),
        re.sub(r"[^a-z0-9]+", " ", term.lower().replace("_", " ")).strip(),
    }
    return any(
        form and re.search(rf"(^|\s){re.escape(form)}($|\s)", normalized_query)
        for form in term_forms
    )


def matched_terms(query: str, collection) -> set[str]:
    return {term for term in _query_terms(collection) if _contains_term(query, term)}


def _query_collection(
    collection,
    query_embedding: list[float],
    n_results: int,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    rows = []
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    for chunk_id, text, metadata, distance in zip(ids, documents, metadatas, distances):
        rows.append(
            {
                "chunk_id": chunk_id,
                "text": text,
                "metadata": metadata or {},
                "distance": float(distance),
            }
        )
    return rows


def retrieve(query: str, k: int = DEFAULT_K) -> list[RetrievalResult]:
    collection = get_collection()
    query_embedding = embed_query(query)
    terms = matched_terms(query, collection)

    candidate_count = max(k * 4, k)
    candidates = _query_collection(collection, query_embedding, candidate_count)

    for term in terms:
        candidates.extend(
            _query_collection(
                collection,
                query_embedding,
                candidate_count,
                where={"term_name": term},
            )
        )

    by_id: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        chunk_id = candidate["chunk_id"]
        if chunk_id not in by_id or candidate["distance"] < by_id[chunk_id]["distance"]:
            by_id[chunk_id] = candidate

    results = []
    for candidate in by_id.values():
        metadata = candidate["metadata"]
        distance = candidate["distance"]
        similarity = 1 - distance
        term_name = str(metadata.get("term_name") or "")
        term_match = term_name in terms
        boosted_similarity = similarity + (TERM_BOOST if term_match else 0)
        results.append(
            RetrievalResult(
                chunk_id=str(metadata.get("chunk_id") or candidate["chunk_id"]),
                title=str(metadata.get("title") or ""),
                term_name=term_name,
                chunk_type=str(metadata.get("chunk_type") or ""),
                url=str(metadata.get("url") or ""),
                text=str(candidate["text"] or ""),
                distance=distance,
                similarity=similarity,
                boosted_similarity=boosted_similarity,
                term_match=term_match,
            )
        )

    return sorted(results, key=lambda item: item.boosted_similarity, reverse=True)[:k]


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def format_results(results: list[RetrievalResult], max_chars: int = DEFAULT_MAX_CHARS) -> str:
    blocks = []
    for index, result in enumerate(results, start=1):
        match_marker = " term_match=yes" if result.term_match else ""
        blocks.append(
            "\n".join(
                [
                    (
                        f"[{index}] distance={result.distance:.4f} "
                        f"similarity={result.similarity:.4f} "
                        f"boosted={result.boosted_similarity:.4f}{match_marker}"
                    ),
                    (
                        f"title={result.title} term_name={result.term_name or '-'} "
                        f"type={result.chunk_type}"
                    ),
                    f"url={result.url}",
                    f"chunk_id={result.chunk_id}",
                    _truncate(result.text, max_chars),
                ]
            )
        )
    return "\n\n".join(blocks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieve relevant PQL documentation chunks.")
    parser.add_argument("query", help="Natural-language query or PQL term to retrieve docs for.")
    parser.add_argument("-k", "--top-k", type=int, default=DEFAULT_K, help="Number of chunks to print.")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help="Maximum characters of chunk text to print per result.",
    )
    args = parser.parse_args(argv)

    try:
        results = retrieve(args.query, k=args.top_k)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(format_results(results, max_chars=args.max_chars))
    return 0

