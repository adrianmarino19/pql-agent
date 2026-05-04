## PQL Agent

### Ask for grounded PQL

The runtime CLI retrieves relevant documentation chunks, asks the model for a
structured answer, validates the result, and appends a JSONL log entry.

```bash
uv run python main.py ask "count cases where activity A happened before activity B"
```

Or use the installed console entrypoint:

```bash
uv run pql-agent ask "count cases where activity A happened before activity B"
```

Optional schema context can be provided inline or from a file:

```bash
uv run python main.py ask "count completed orders by region" \
  --schema '"Orders"."region", "Orders"."status", "Orders"."case_id"'

uv run python main.py ask "count completed orders by region" --schema-file schema.txt
```

The response shape is:

```json
{
  "query": "...",
  "explanation": "...",
  "cited_chunks": ["..."],
  "validation": {
    "status": "passed",
    "warnings": []
  }
}
```

### Retrieve docs

To inspect retrieval without generation:

```bash
uv run python main.py retrieve "MATCH_PROCESS_REGEX" --top-k 3
```

### Scrape docs

The scraper discovers pages from the sidebar of:

`https://docs.celonis.com/en/pql---process-query-language.html`

It then fetches those pages in order, includes `comments.html`, and writes JSONL output with cleaned `full_content` ready for embedding.

```bash
uv run python scripts/scrape_docs.py
```

Useful options:

```bash
uv run python scripts/scrape_docs.py --out data/scrape/pql_docs.jsonl --workers 8 --delay 0.1 --timeout 20 --max-pages 10

# Also archive raw HTML for reproducible re-parsing:
uv run python scripts/scrape_docs.py --raw-dir data/raw/
```

Each JSONL record includes:
- `url`
- `source`
- `position`
- `status_code`
- `fetched_at_utc`
- `title`
- `full_content`
- `content_hash_sha256`
- `word_count`
- `error` (only on failures)

Notes:
- Fetching is parallel (`--workers`, default `8`).
- Transient failures are retried automatically (`3` attempts with exponential backoff).
- Output JSONL is still written in original sidebar order.
