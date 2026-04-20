# PQL Agent — Chunking Strategy

Grounded in corpus analysis of `data/scrape/pql_docs.jsonl` (291 pages).

---

## Key Findings

| Signal | Value |
|---|---|
| Total pages | 291 |
| Median page | 370 words / 624 tokens |
| Pages with Syntax block | ~84% |
| Pages with `[n]` example markers | 245 (84%) |
| Concept pages (no Syntax block) | 46 (16%) |
| Mean examples per page (all pages) | 3.56 |
| Median examples per page (all pages) | 3 |
| Mean examples per page (pages with examples) | 4.23 |
| Median examples per page (pages with examples) | 4 |
| Mean description+syntax token size | 240 tokens |
| Median description+syntax token size | 168 tokens |

The corpus is almost entirely **PQL function reference pages** with a consistent
structure: `Description → Syntax → [n] example blocks → Result / Tips / Warnings`.
The 46 concept pages (~16%) are prose guides with no `Syntax` block.

The dominant source of page bloat is **stacked example blocks**, not description
or syntax content. Description+syntax sections average only 240 tokens and have a
median of 168 tokens. Splitting on example boundaries is therefore the correct
structural approach, not a fixed token window.

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
| `full` | Entire page as one chunk | Page ≤ 600 tokens, or > 600 tokens with no `[n]` markers |
| `description_syntax` | Description + Syntax section only | Pages > 600 tokens with `[n]` markers — always the first chunk |
| `example` | One or more consecutive `[n]` example blocks | Pages > 600 tokens with `[n]` markers — greedy-packed up to 400 tokens |
| `concept` | Prose guide page, no Syntax block | Concept/guide pages (~16% of corpus) |

---

## Splitting Logic

### Atomic unit rules

- **`Description` and `Syntax` must never be separated.** They are the minimum
  viable context for generation and always live in their own `description_syntax`
  chunk.
- **A single example block is never split.** If one example exceeds the 400-token
  target on its own, it becomes its own chunk at whatever size it is.

---

### Case 1 — page ≤ 600 tokens

Keep as a single `full` chunk. Splitting at this size adds noise without improving
retrieval precision.

```
chunk_type: full
text:       entire page content (normalized)
```

---

### Case 2 — page > 600 tokens, no `[n]` markers

No structural signal to split on. Keep as a single `full` chunk.

```
chunk_type: full
text:       entire page content (normalized)
```

---

### Case 3 — page > 600 tokens, has `[n]` markers

Split structurally on example boundaries.

**Chunk 1** — `description_syntax`: everything before the first `[1]` block.
Always its own chunk — kept isolated so "what does X do?" queries retrieve a
clean, focused target without example noise diluting the embedding.

```
chunk_type: description_syntax
text:
  <Description text>
  Syntax: MATCH_PROCESS_REGEX(activity_table.string_column, regular_expression)
  <Parameter descriptions>
```

**Chunks 2..N** — `example`: greedy accumulator. Pack consecutive example blocks
until adding the next would push the chunk over 400 tokens, then flush and start
a new chunk. Every example chunk is prepended with the function name and syntax
signature so it is fully self-contained at retrieval time.

```
chunk_type: example
example_index_start: 2
example_index_end:   3
text:
  Function: MATCH_PROCESS_REGEX
  Syntax: MATCH_PROCESS_REGEX(activity_table.string_column, regular_expression)

  [2] Filter with exact string
  Query: FILTER MATCH_PROCESS_REGEX(...) = 1;
  Input: ...
  Result: ...

  [3] Filter with sequence pattern
  Query: FILTER MATCH_PROCESS_REGEX(...) = 1;
  Input: ...
  Result: ...
```

---

### Case 4 — concept page (no Syntax block)

Keep as a single `concept` chunk regardless of size. Sliding window is the right
long-term answer for large prose pages but these 46 pages are a small enough share
of the corpus to defer.

```
chunk_type: concept
text:       entire page content (normalized)
```

---

## Token Budget Rationale

| Constant | Value | Reason |
|---|---|---|
| `FULL_CHUNK_MAX` | 600 tokens | Below this, splitting adds noise. Median page is 624 tokens so the threshold is calibrated to the corpus. |
| `EXAMPLE_CHUNK_TARGET` | 400 tokens | Retrieval precision peaks at 256–512 tokens across RAG benchmarks. 400 is chosen over the lower end because PQL examples include structured input/output tables that are denser than prose. |

---

## Corpus Output (291 pages → 821 chunks)

| `chunk_type` | Count | Mean tokens | Median tokens |
|---|---|---|---|
| `full` | 106 | 355 | 339 |
| `concept` | 65 | 894 | 304 |
| `description_syntax` | 120 | 358 | 291 |
| `example` | 530 | 448 | 344 |

128 of the 530 example chunks contain two or more merged examples.
402 example chunks contain a single example (including large outliers that
exceeded the 400-token target on their own, e.g. `WORKDAY_CALENDAR` example [3]
at 16 393 tokens).

---

## Chunk Metadata Schema

Every chunk, regardless of type, carries:

| Field | Type | Description |
|---|---|---|
| `chunk_id` | `str` | Stable hash of `url + chunk_type + example_index_start` |
| `url` | `str` | Source page URL (for citation) |
| `title` | `str` | Page title / function name |
| `term_name` | `str \| null` | Canonical named PQL term, derived from `Syntax` block first and strict title fallback second |
| `chunk_type` | `str` | `full` \| `description_syntax` \| `example` \| `concept` |
| `example_index_start` | `int \| null` | Index of first `[n]` block in this chunk; `null` for non-example chunks |
| `example_index_end` | `int \| null` | Index of last `[n]` block in this chunk; equals `example_index_start` for single-example chunks; `null` for non-example chunks |
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
