from dataclasses import dataclass


@dataclass
class Answer:
    query: str
    explanation: str
    cited_chunks: list[str]


@dataclass
class ValidationResult:
    status: str
    warnings: list[str]

