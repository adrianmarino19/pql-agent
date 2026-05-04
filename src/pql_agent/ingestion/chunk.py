import hashlib
import json
import re

import tiktoken

ENCODING = tiktoken.get_encoding("cl100k_base")
TIER3_MIN = 2048


def build_pql_dict(jsonl_path: str) -> set[str]:
    """Return PQL functions, inferred from all-caps identifiers in the corpus."""
    pql_functions: set[str] = set()
    with open(jsonl_path) as f:
        for line in f:
            doc = json.loads(line)
            hits = re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", doc.get("full_content", ""))
            pql_functions.update(hits)
    return pql_functions


def normalize_pql(text: str, pql_dict: set[str]) -> str:
    """Normalize PQL function names for embedding search."""
    for fn in sorted(pql_dict, key=len, reverse=True):
        text = text.replace(fn, fn.lower().replace("_", " "))
    return text


def count_tokens(text: str) -> int:
    return len(ENCODING.encode(text))


def chunk_id(url: str, chunk_type: str, example_index) -> str:
    key = f"{url}:{chunk_type}:{example_index}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def extract_syntax_signature(content: str, title: str) -> str | None:
    """Extract function syntax to prepend to separately chunked examples."""
    pattern = rf"Syntax\s+({re.escape(title)}\s*\([^)]*\))"
    m = re.search(pattern, content)
    return m.group(1).strip() if m else None


def extract_syntax_term(content: str) -> str | None:
    """Extract the leading named term from the Syntax block, if present."""
    m = re.search(r"\bSyntax\s+([A-Z][A-Z0-9_]*)\b", content)
    return m.group(1).strip() if m else None


def title_looks_like_term(title: str) -> bool:
    """Return True when a title looks like a named PQL term, not prose."""
    cleaned = title.strip()
    if not cleaned or " " in cleaned:
        return False
    return bool(re.fullmatch(r"[A-Z][A-Z0-9_]*", cleaned))


def derive_term_name(title: str, content: str) -> str | None:
    """Derive a canonical PQL term from syntax first, then strict title fallback."""
    syntax_term = extract_syntax_term(content)
    if syntax_term:
        return syntax_term
    if title_looks_like_term(title):
        return title.strip()
    return None


def _make_chunk(
    url: str,
    title: str,
    term_name: str | None,
    chunk_type: str,
    text: str,
    example_index=None,
) -> dict:
    return {
        "chunk_id": chunk_id(url, chunk_type, example_index),
        "url": url,
        "title": title,
        "term_name": term_name,
        "chunk_type": chunk_type,
        "example_index": example_index,
        "word_count": len(text.split()),
        "token_count": count_tokens(text),
        "text": text,
    }


def chunk_page(doc: dict, pql_dict: set[str]) -> list[dict]:
    url = doc["url"]
    title = doc.get("title", "")
    raw_content = doc.get("full_content", "")
    term_name = derive_term_name(title, raw_content)

    has_syntax = bool(re.search(r"\bSyntax\b", raw_content))
    has_examples = bool(re.search(r"\[1\]", raw_content))
    n_tokens = count_tokens(raw_content)

    if not has_syntax:
        return [_make_chunk(url, title, term_name, "concept", normalize_pql(raw_content, pql_dict))]

    if n_tokens <= TIER3_MIN:
        return [_make_chunk(url, title, term_name, "full", normalize_pql(raw_content, pql_dict))]

    if not has_examples:
        return [_make_chunk(url, title, term_name, "full", normalize_pql(raw_content, pql_dict))]

    syntax_sig = extract_syntax_signature(raw_content, title)
    prefix_raw = f"Function: {title}"
    if syntax_sig:
        prefix_raw += f"\nSyntax: {syntax_sig}"
    prefix = normalize_pql(prefix_raw, pql_dict)

    seq_markers: list[tuple[int, int, int]] = []
    expected = 1
    for m in re.finditer(r"\[(\d+)\]", raw_content):
        if int(m.group(1)) == expected:
            seq_markers.append((m.start(), m.end(), expected))
            expected += 1

    if not seq_markers:
        return [_make_chunk(url, title, term_name, "full", normalize_pql(raw_content, pql_dict))]

    chunks = []

    desc_text = normalize_pql(raw_content[: seq_markers[0][0]].strip(), pql_dict)
    chunks.append(_make_chunk(url, title, term_name, "description_syntax", desc_text))

    for i, (start, _end, idx) in enumerate(seq_markers):
        next_start = seq_markers[i + 1][0] if i + 1 < len(seq_markers) else len(raw_content)
        ex_text = normalize_pql(raw_content[start:next_start].strip(), pql_dict)
        full_ex = f"{prefix}\n\n{ex_text}"
        chunks.append(_make_chunk(url, title, term_name, "example", full_ex, example_index=idx))

    return chunks

