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
- [ ] Ingestion pipeline (chunk + embed + vector store) not implemented yet.
- [ ] Runtime query assistant (retrieval + prompt + generation) not implemented yet.

## Phase 1 — Ingestion

### 1) Source Acquisition

- [x] Add root-doc scraper entrypoint (`scripts/scrape_docs.py`).
- [x] Restrict discovery to PQL pages only.
- [x] Include `comments.html` in scope.
- [x] Add retry/backoff and failure capture per page.

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

- [ ] Implement chunker module — chunk by function or concept, not fixed token window alone.
- [ ] Keep syntax blocks and examples together within the same chunk.
- [ ] Add chunk metadata:
  - `chunk_id`, `url`, `title`, `function_name` (if detectable)
  - `category`, `doc_version`
  - `section_type`: one of `syntax`, `parameter`, `example`, `note`
- [ ] Export chunk JSONL for embedding pipeline.

### 5) Embedding + Vector Store

- [ ] Add embedding script (OpenAI embedding model).
- [ ] Persist embeddings to local Chroma store.
- [ ] Add idempotent re-run behavior (skip unchanged by content hash).
- [ ] Add quick retrieval smoke test (`top-k` by sample query).

## Phase 2 — Runtime Assistant

### 1) Retrieval

- [ ] Implement retriever module: query embed -> Chroma similarity search.
- [ ] Return top-k chunks + chunk metadata.
- [ ] Add tuning knobs (`k`, score threshold).
- [ ] Add keyword fallback for exact function name matches (via Chroma `where` filters on `function_name` metadata).

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

- [ ] Improve chunking based on observed failures.
- [ ] Add few-shot examples for high-frequency intents.
- [ ] Add hybrid search (dense + keyword) if pure semantic search feels noisy.
- [ ] Add syntax-aware validator (later stage).
- [ ] Consider fine-tuning only after enough high-quality logs.

## Environment Checklist

- [ ] `OPENAI_API_KEY` configured

## Runbook (Current)

- [x] Scrape PQL docs:

```bash
python scripts/scrape_docs.py
```

- [ ] Build chunk dataset
- [ ] Build embeddings/vector store
- [ ] Launch CLI runtime
- [ ] Launch Streamlit app
