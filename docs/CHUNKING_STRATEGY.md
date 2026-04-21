# PQL Agent — Chunking Strategy

Grounded in corpus analysis of `data/scrape/pql_docs.jsonl` (291 pages).
See `notebooks/chunking_analysis.ipynb` for the full analysis.

---

## Key Findings

| Signal | Value |
|---|---|
| Total pages | 291 |
| Median page | 370 words / 624 tokens |
| Pages with Description + Syntax + Examples | ~80% |
| Pages ≤ 512 tokens | 44% |
| Pages ≤ 1024 tokens | 63% |
| Pages ≤ 2048 tokens | 84% |
| Pages > 2048 tokens (must split) | 16% |

The corpus is almost entirely **PQL function reference pages** with a consistent
structure: `Description → Syntax → [n] example blocks → Result / Tips / Warnings`.
The remaining pages (~20%) are prose concept guides with no `Syntax` block.

---

## Pre-processing: PQL Dictionary (do this before chunking and embedding)

The `cl100k_base` tokenizer splits PQL function names on underscores:
`MATCH_PROCESS_REGEX` → `MATCH`, `_`, `PROCESS`, `_`, `REGEX`.
This destroys retrieval signal — a query for "filter by process regex" must fire
on the function name as a unit.

**Step 1 — Build the dictionary.** Extract all-caps underscore-separated
identifiers from `full_content` across all pages:

```python
import re, json

pql_functions = set()
with open('data/scrape/pql_docs.jsonl') as f:
    for line in f:
        doc = json.loads(line)
        hits = re.findall(r'\b[A-Z][A-Z0-9_]{2,}\b', doc.get('full_content', ''))
        pql_functions.update(hits)
```

**Step 2 — Normalize before embedding.** If using a hosted embedding API
(OpenAI, Cohere) where special tokens cannot be injected, lowercase-normalize
all function names in chunk text before embedding:

```python
def normalize_pql(text: str, pql_dict: set[str]) -> str:
    for fn in sorted(pql_dict, key=len, reverse=True):
        text = text.replace(fn, fn.lower().replace('_', ' '))
    return text
```

`MATCH_PROCESS_REGEX` → `match process regex` — meaningful sub-tokens instead
of punctuation fragments.

If using a local tokenizer, register function names as special tokens instead.

---

## Chunk Types

Every chunk carries a `chunk_type` field:

| `chunk_type` | Description | When used |
|---|---|---|
| `full` | Entire page as one chunk | Tiers 1 & 2 — page fits within token budget |
| `description_syntax` | Description + Syntax section only | Tier 3 — large pages, always the first chunk |
| `example` | One numbered `[n]` example block | Tier 3 — each example becomes its own chunk |
| `concept` | Prose guide page, no Syntax block | Concept/guide pages (~20% of corpus) |

---

## Three-Tier Splitting Logic

### Atomic unit rule

**`Description` and `Syntax` must never be separated.** They are the minimum
viable context for generation. An example without its syntax signature is
ambiguous; a syntax without a description is incomplete.

---

### Tier 1 — pages ≤ 600 tokens (≈ 44% of corpus)

Keep as a single `full` chunk. No splitting needed.

```
chunk_type: full
text:       entire page content (normalized)
```

---

### Tier 2 — pages 600–2048 tokens (≈ 40% of corpus)

Keep as a single `full` chunk where possible. If the page is at the upper end
and content is clearly separable, it may be split exactly as Tier 3, but prefer
keeping it whole — these pages are coherent and fit within any practical context
window.

```
chunk_type: full
text:       entire page content (normalized)
```

---

### Tier 3 — pages > 2048 tokens (≈ 16% of corpus)

Split by numbered example blocks (`[1]`, `[2]`, `[3]`, …).

**Chunk 1** — `description_syntax`: everything before the first `[n]` block.

```
chunk_type: description_syntax
text:
  Function: MATCH_PROCESS_REGEX
  <Description text>
  Syntax: MATCH_PROCESS_REGEX(activity_table.string_column, regular_expression)
  <Parameter descriptions>
```

**Chunk 2..N** — `example`: one per `[n]` block, prepended with the function
name and syntax signature so the chunk is self-contained at retrieval time.

```
chunk_type: example
example_index: 3
text:
  Function: MATCH_PROCESS_REGEX
  Syntax: MATCH_PROCESS_REGEX(activity_table.string_column, regular_expression)

  [Example 3]: Filter with sequence pattern
  Query: FILTER MATCH_PROCESS_REGEX(...) = 1;
  Input: ...
  Result: ...
```

Prepending the function name and syntax to every example chunk is critical —
it ensures the chunk is retrievable and interpretable in isolation without
needing to fetch sibling chunks at query time.

---

## Chunk Metadata Schema

Every chunk, regardless of tier or type, must carry:

| Field | Type | Description |
|---|---|---|
| `chunk_id` | `str` | Stable hash of `url + chunk_type + example_index` |
| `url` | `str` | Source page URL (for citation) |
| `title` | `str` | Page title / function name |
| `term_name` | `str \| null` | Canonical named PQL term for the page, derived from `Syntax` first and strict title fallback second |
| `chunk_type` | `str` | `full` \| `description_syntax` \| `example` \| `concept` |
| `example_index` | `int \| null` | Which `[n]` block; `null` for non-example chunks |
| `word_count` | `int` | Word count of the chunk text |
| `token_count` | `int` | Token count after normalization |

---

## Retrieval Implications

`chunk_type` is useful beyond storage — it can bias retrieval at query time:

- *"What does X do?"* → prefer `description_syntax` and `concept` chunks.
- *"Show me how to use X"* or *"give me an example"* → prefer `example` chunks.
- When a `full` chunk is retrieved, the caller knows it has complete page context
  and no sibling chunks need to be fetched.

For v1, plain vector search is sufficient. For v2, hybrid retrieval (dense +
keyword match on `title` / `term_name` metadata) will improve precision for
exact function name lookups, which is the dominant user intent in this corpus.
