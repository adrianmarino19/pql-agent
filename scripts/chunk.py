import hashlib
import json
import re

import tiktoken

ENCODING = tiktoken.get_encoding("cl100k_base")

# Pages at or below this token count are kept as a single full chunk.
# Splitting gains little at this size and adds noise.
FULL_CHUNK_MAX = 600

# Target token ceiling for each example chunk (greedy accumulator).
# A single example that already exceeds this is kept as its own chunk —
# we never split within an example.
EXAMPLE_CHUNK_TARGET = 400


def build_pql_dict(jsonl_path: str) -> set[str]:
    """Return a set with the PQL functions, assumed from vocabulary that is in CAPS in corpus."""
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
    """Extract function and syntax per page to append to examples, if chunked separately."""
    # Stop at first closing paren — scraped text has no newlines so [^\n]* grabs entire page
    pattern = rf'Syntax\s+({re.escape(title)}\s*\([^)]*\))'
    m = re.search(pattern, content)
    return m.group(1).strip() if m else None


def extract_syntax_term(content: str) -> str | None:
    """Extract the leading named term from the Syntax block, if present."""
    m = re.search(r'\bSyntax\s+([A-Z][A-Z0-9_]*)\b', content)
    return m.group(1).strip() if m else None


def title_looks_like_term(title: str) -> bool:
    """Return True when a title looks like a named PQL term, not prose."""
    cleaned = title.strip()
    if not cleaned or " " in cleaned:
        return False
    return bool(re.fullmatch(r'[A-Z][A-Z0-9_]*', cleaned))


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
    example_index_start=None,
    example_index_end=None,
) -> dict:
    return {
        "chunk_id": chunk_id(url, chunk_type, example_index_start),
        "url": url,
        "title": title,
        "term_name": term_name,
        "chunk_type": chunk_type,
        "example_index_start": example_index_start,
        "example_index_end": example_index_end,
        "word_count": len(text.split()),
        "token_count": count_tokens(text),
        "text": text,
    }


def _flush_example_chunk(
    url: str,
    title: str,
    term_name: str | None,
    prefix: str,
    acc_indices: list[int],
    acc_texts: list[str],
    pql_dict: set[str],
) -> dict:
    """Combine accumulated example texts with the prefix and return a chunk."""
    combined = prefix + "\n\n" + "\n\n".join(acc_texts)
    return _make_chunk(
        url, title, term_name, "example",
        normalize_pql(combined, pql_dict),
        example_index_start=acc_indices[0],
        example_index_end=acc_indices[-1],
    )


def chunk_page(doc: dict, pql_dict: set[str]) -> list[dict]:
    url = doc["url"]
    title = doc.get("title", "")
    raw_content = doc.get("full_content", "")
    term_name = derive_term_name(title, raw_content)

    has_syntax = bool(re.search(r'\bSyntax\b', raw_content))
    n_tokens = count_tokens(raw_content)

    # Case 4 — concept page: no Syntax block (prose guide).
    # Keep as single concept chunk regardless of size.
    if not has_syntax:
        return [_make_chunk(url, title, term_name, "concept", normalize_pql(raw_content, pql_dict))]

    # Case 1 — small page: at or below token budget.
    # Splitting gains nothing at this size.
    if n_tokens <= FULL_CHUNK_MAX:
        return [_make_chunk(url, title, term_name, "full", normalize_pql(raw_content, pql_dict))]

    # Collect only sequential [n] markers (skips false positives like [1904])
    seq_markers: list[tuple[int, int, int]] = []
    expected = 1
    for m in re.finditer(r'\[(\d+)\]', raw_content):
        if int(m.group(1)) == expected:
            seq_markers.append((m.start(), m.end(), expected))
            expected += 1

    # Case 2 — large page with no example markers: no structural signal to split on.
    if not seq_markers:
        return [_make_chunk(url, title, term_name, "full", normalize_pql(raw_content, pql_dict))]

    # Case 3 — large page with example markers: split structurally.
    #
    # Chunk 1: description_syntax — everything before [1]. Always its own chunk
    # so that "what does X do?" queries retrieve a clean, focused target.
    #
    # Chunks 2..N: greedy accumulator. Pack examples up to EXAMPLE_CHUNK_TARGET
    # tokens each. A single example that already exceeds the target is kept alone —
    # we never split within an example. Every example chunk is prepended with the
    # function name and syntax signature so it is self-contained at retrieval time.

    syntax_sig = extract_syntax_signature(raw_content, title)
    prefix_raw = f"Function: {title}"
    if syntax_sig:
        prefix_raw += f"\nSyntax: {syntax_sig}"
    prefix = normalize_pql(prefix_raw, pql_dict)
    prefix_tokens = count_tokens(prefix) + 2  # +2 for the trailing \n\n separator

    chunks: list[dict] = []

    desc_text = normalize_pql(raw_content[: seq_markers[0][0]].strip(), pql_dict)
    chunks.append(_make_chunk(url, title, term_name, "description_syntax", desc_text))

    acc_indices: list[int] = []
    acc_texts: list[str] = []
    acc_tokens = prefix_tokens

    for i, (start, _end, idx) in enumerate(seq_markers):
        next_start = seq_markers[i + 1][0] if i + 1 < len(seq_markers) else len(raw_content)
        ex_text = raw_content[start:next_start].strip()
        ex_tokens = count_tokens(ex_text)

        # Flush current accumulator if adding this example would exceed the target
        # and we already have at least one example buffered.
        if acc_texts and acc_tokens + ex_tokens > EXAMPLE_CHUNK_TARGET:
            chunks.append(_flush_example_chunk(url, title, term_name, prefix, acc_indices, acc_texts, pql_dict))
            acc_indices = []
            acc_texts = []
            acc_tokens = prefix_tokens

        acc_indices.append(idx)
        acc_texts.append(ex_text)
        acc_tokens += ex_tokens + 2  # +2 for \n\n between examples

    # Flush any remaining examples
    if acc_texts:
        chunks.append(_flush_example_chunk(url, title, term_name, prefix, acc_indices, acc_texts, pql_dict))

    return chunks
