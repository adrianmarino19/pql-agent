import hashlib
import json
import re

import tiktoken

ENCODING = tiktoken.get_encoding("cl100k_base")
TIER3_MIN = 2048


def build_pql_dict(jsonl_path: str) -> set[str]:
    """Return a dictionary with the PQL functions, assumed from vocabulary that is in CAPS in corpus."""
    pql_functions: set[str] = set()
    with open(jsonl_path) as f:
        for line in f:
            doc = json.loads(line)
            hits = re.findall(r'\b[A-Z][A-Z0-9_]{2,}\b', doc.get('full_content', ''))
            pql_functions.update(hits)
    return pql_functions


def normalize_pql(text: str, pql_dict: set[str]) -> str:
    """Normalize (lowercase) functions from PQL function dict."""
    for fn in sorted(pql_dict, key=len, reverse=True):
        text = text.replace(fn, fn.lower().replace('_', ' '))
    return text


def count_tokens(text: str) -> int:
    return len(ENCODING.encode(text))


def chunk_id(url: str, chunk_type: str, example_index) -> str:
    key = f"{url}:{chunk_type}:{example_index}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def extract_syntax_signature(content: str, title: str) -> str | None:
    """Extract function and syntax per page to append to examples, if chunked separately"""
    # Stop at first closing paren — scraped text has no newlines so [^\n]* grabs entire page
    pattern = rf'Syntax\s+({re.escape(title)}\s*\([^)]*\))'
    m = re.search(pattern, content)
    return m.group(1).strip() if m else None


def _make_chunk(url: str, title: str, chunk_type: str, text: str, example_index=None) -> dict:
    return {
        "chunk_id": chunk_id(url, chunk_type, example_index),
        "url": url,
        "title": title,
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

    has_syntax = bool(re.search(r'\bSyntax\b', raw_content))
    has_examples = bool(re.search(r'\[1\]', raw_content))
    n_tokens = count_tokens(raw_content)

    # Concept page: no Syntax block (prose guide, any tier)
    if not has_syntax:
        return [_make_chunk(url, title, "concept", normalize_pql(raw_content, pql_dict))]

    # Tier 1 & 2: keep as single full chunk
    if n_tokens <= TIER3_MIN:
        return [_make_chunk(url, title, "full", normalize_pql(raw_content, pql_dict))]

    # Tier 3 with no example blocks: can't split, keep as full
    if not has_examples:
        return [_make_chunk(url, title, "full", normalize_pql(raw_content, pql_dict))]

    # Tier 3 with example blocks: split on [n] markers
    syntax_sig = extract_syntax_signature(raw_content, title)
    prefix_raw = f"Function: {title}"
    if syntax_sig:
        prefix_raw += f"\nSyntax: {syntax_sig}"
    prefix = normalize_pql(prefix_raw, pql_dict)

    # Collect only sequential [n] markers (skips false positives like [1904])
    seq_markers: list[tuple[int, int, int]] = []
    expected = 1
    for m in re.finditer(r'\[(\d+)\]', raw_content):
        if int(m.group(1)) == expected:
            seq_markers.append((m.start(), m.end(), expected))
            expected += 1

    if not seq_markers:
        return [_make_chunk(url, title, "full", normalize_pql(raw_content, pql_dict))]

    chunks = []

    desc_text = normalize_pql(raw_content[: seq_markers[0][0]].strip(), pql_dict)
    chunks.append(_make_chunk(url, title, "description_syntax", desc_text))

    for i, (start, _end, idx) in enumerate(seq_markers):
        next_start = seq_markers[i + 1][0] if i + 1 < len(seq_markers) else len(raw_content)
        ex_text = normalize_pql(raw_content[start:next_start].strip(), pql_dict)
        full_ex = f"{prefix}\n\n{ex_text}"
        chunks.append(_make_chunk(url, title, "example", full_ex, example_index=idx))

    return chunks
