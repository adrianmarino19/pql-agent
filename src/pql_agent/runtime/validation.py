import re

from pql_agent.retrieval.retrieve import RetrievalResult
from pql_agent.runtime.models import Answer, ValidationResult


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
