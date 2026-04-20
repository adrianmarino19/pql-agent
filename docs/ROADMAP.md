# PQL Agent — Build Checklist

Use this file as the execution tracker for the PQL assistant.
Mark tasks as done when completed.

## Goal

- [ ] Ship a PQL assistant that converts natural language into grounded PQL using Celonis docs.
- [ ] Ensure answers are based on retrieved documentation (not hallucinated syntax).
- [ ] Log usage for evaluation and iteration.

## Current Status Snapshot

- [x] Initial scraper implemented.
- [x] Scraper parallelized for speed (`--workers`).
- [x] Scraper scope fixed to PQL docs only (`taxonomy_celonis_pql`).
- [x] Scraped text cleanup added (removed nav/feedback boilerplate and `\n` in `full_content`).
- [x] **Chunking strategy revised** — structure-first greedy accumulator replacing the old 2048-token tier approach.
- [x] **Ingestion pipeline complete** (chunk + embed + vector store).
- [ ] Runtime query assistant (retrieval + prompt + generation) not implemented yet.

## Phase 1 — Ingestion

### 1) Source Acquisition

- [x] Add root-doc scraper entrypoint (`scripts/scrape_docs.py`).
- [x] Restrict discovery to PQL pages only.
- [x] Include `comments.html` in scope.
- [x] Add retry/backoff and failure capture per page.
- [x] Add optional raw HTML archival (`--raw-dir`, saves `<content_hash>.html` per page).

### 2) Content Cleanup and Normalization

- [x] Extract title + cleaned `full_content` for each page.
- [x] Remove repeated UI boilerplate:
  - `Prev`, `Next`
  - `Search results`, `No results found`
  - feedback block
- [x] Normalize content to single-line text (no `\n` in stored `full_content`).

### 3) Structured Outputs

- [x] Write JSONL with metadata fields:
  - `url`, `source`, `position`, `status_code`, `fetched_at_utc`
  - `title`, `full_content`, `content_hash_sha256`, `word_count`, `error`
- [ ] Add schema validation check before writing output.

### 4) Chunking

- [x] **Implement chunker module** (`scripts/chunk.py`):
  - [x] Structure-first four-case logic (see `docs/CHUNKING_STRATEGY.md`):
    - Pages ≤ 600 tokens → single `full` chunk.
    - Pages > 600 tokens, no `[n]` markers → single `full` chunk (no structural signal).
    - Pages > 600 tokens, has `[n]` markers → `description_syntax` chunk + greedy example chunks (target 400 tokens each).
    - No `Syntax` block → single `concept` chunk.
  - [x] `description_syntax` always its own isolated chunk — keeps "what does X do?" retrieval clean.
  - [x] Greedy accumulator for examples: packs consecutive `[n]` blocks up to 400 tokens; oversized single examples kept as-is.
  - [x] PQL dictionary normalization: `MATCH_PROCESS_REGEX` → `match process regex` before embedding (improves tokenization).
  - [x] Sequential marker validation to skip false positives (`[1904]` inside example text).
  - [x] Chunk metadata: `chunk_id` (SHA256 hash of url+chunk_type+example_index_start), `url`, `title`, `term_name`, `chunk_type`, `example_index_start`, `example_index_end`, `word_count`, `token_count`, `text`.
  - Result: **821 chunks** from 291 pages (65 concept, 106 full, 120 description_syntax, 530 example).

### 5) Embedding + Vector Store

- [x] **Add embedding script** (`scripts/embed.py`):
  - [x] Batch OpenAI API calls (batches of 100 chunks).
  - [x] Model: `text-embedding-3-small` (1536 dimensions).
  - [x] Token truncation at 8191 (API limit); 1 chunk exceeds this and will be truncated.
- [x] **Orchestrate pipeline** (`scripts/pipeline.py`):
  - [x] Load JSONL → build PQL dict → chunk → embed → upsert into Chroma at `data/chroma/`.
  - [x] Chroma collection: `pql_docs`, cosine similarity, local persistent store.
- [ ] Add idempotent re-run behavior (skip unchanged by content hash).
- [ ] Add quick retrieval smoke test (`top-k` by sample query).

## Phase 2 — Runtime Assistant

### 1) Retrieval

- [ ] Implement retriever module: query embed -> Chroma similarity search.
- [ ] Return top-k chunks + chunk metadata.
- [ ] Add tuning knobs (`k`, score threshold).
- [ ] Add keyword fallback for exact PQL term matches (via Chroma `where` filters on `term_name` metadata).

### 2) CLI runtime (before UI)

- [ ] Build CLI script: takes a natural-language question, prints structured response.
- [ ] Use CLI to iterate on prompt and retrieval quality before building UI.

### 3) Prompting + Generation

- [ ] Implement prompt builder with strict grounding instructions.
- [ ] Require output contract:
  - `query`
  - `explanation`
  - `assumptions`
  - `missing_context`
  - `cited_chunks`
- [ ] Integrate OpenAI chat model call.

### 4) Schema Context Input

- [ ] Allow user to provide table/column schema as input (e.g. paste schema text).
- [ ] Inject schema context into prompt alongside retrieved chunks.
- [ ] When schema is missing and required, surface it in `missing_context`.

### 5) Validation Layer

- [ ] Add lightweight response checks:
  - non-empty query
  - output format valid
  - cited chunks present
  - referenced functions appear in retrieved docs
  - flag unresolved placeholders
- [ ] Add warning path when context is insufficient.

### 6) UI

- [ ] Build Streamlit app for ask -> retrieve -> generate flow.
- [ ] Show generated query + explanation + assumptions.
- [ ] Show cited documentation chunks to user.

## Phase 3 — Logging, Evaluation, Iteration

### 1) Logging

- [ ] Add query logging sink (local JSONL or SQLite).
- [ ] Log fields:
  - `timestamp`, `session_id`, `question`
  - `retrieved_chunk_ids`, `retrieval_titles`, `generated_query`
  - `assumptions`, `missing_context`
  - `model`, `validation_status`
  - `user_feedback` (optional thumbs up/down)

### 2) Evaluation

- [ ] Define initial eval set from logged real queries.
- [ ] Add manual quality rubric:
  - syntax plausibility
  - grounding quality
  - business usefulness
- [ ] Run weekly review on failure cases.

### 3) Iteration Roadmap

- [ ] Improve chunking based on observed failures (next candidate: sliding window for large concept pages).
- [ ] Add few-shot examples for high-frequency intents.
- [ ] Add hybrid search (dense + keyword) if pure semantic search feels noisy.
- [ ] Add syntax-aware validator (later stage).
- [ ] Consider fine-tuning only after enough high-quality logs.

## Environment Checklist

- [x] `OPENAI_API_KEY` configured (required for embedding pipeline)

## Runbook (v1 Ingestion Complete)

### Scrape PQL docs (already done, 291 pages in `data/scrape/pql_docs.jsonl`)
```bash
python scripts/scrape_docs.py
```

### Build embeddings and vector store (new)
```bash
export OPENAI_API_KEY=sk-...
uv run python scripts/pipeline.py
```
This will:
1. Load 291 pages from `data/scrape/pql_docs.jsonl`
2. Build a PQL function dictionary (701 identifiers)
3. Chunk pages using the structure-first greedy strategy → 821 chunks
4. Embed with OpenAI `text-embedding-3-small`
5. Upsert into Chroma at `data/chroma/pql_docs`
6. Print summary: elapsed time, total chunks stored

**Next steps:**
- [ ] Launch CLI runtime (retriever + prompt + generator + validator)
- [ ] Launch Streamlit app
