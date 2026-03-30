## PQL Agent

### Scrape docs

The scraper discovers pages from the sidebar of:

`https://docs.celonis.com/en/pql---process-query-language.html`

It then fetches those pages in order, includes `comments.html`, and writes JSONL output with cleaned `full_content` ready for embedding.

```bash
python scripts/scrape_docs.py
```

Useful options:

```bash
python scripts/scrape_docs.py --out data/scrape/pql_docs.jsonl --workers 8 --delay 0.1 --timeout 20 --max-pages 10
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
