from dataclasses import dataclass
from typing import Any


@dataclass
class Answer:
    query: str
    explanation: str
    cited_chunks: list[str]


@dataclass
class ValidationResult:
    status: str
    warnings: list[str]


@dataclass
class ToolCallTrace:
    tool_name: str
    query: str
    k: int
    retrieved_chunk_ids: list[str]
    results: list[dict[str, Any]]
