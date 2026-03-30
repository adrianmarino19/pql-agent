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
- [ ] Add optional raw HTML archival (`data/raw/`) for reproducible parsing.
- [ ] Add robots.txt / crawl-policy verification step.

### 2) Content Cleanup and Normalization

- [x] Extract title + cleaned `full_content` for each page.
- [x] Remove repeated UI boilerplate:
  - `Prev`, `Next`
  - `Search results`, `No results found`
  - feedback block
- [x] Normalize content to single-line text (no `\n` in stored `full_content`).
- [ ] Add optional `cleaned_markdown` output for chunking readability.

### 3) Structured Outputs

- [x] Write JSONL with metadata fields:
  - `url`, `source`, `position`, `status_code`, `fetched_at_utc`
  - `title`, `full_content`, `content_hash_sha256`, `word_count`, `error`
- [ ] Define and freeze v1 schema contract in code comments/docs.
- [ ] Add schema validation check before writing output.

### 4) Chunking

- [ ] Implement chunker module (`function/section` oriented, not fixed-size only).
- [ ] Keep syntax/examples together where possible.
- [ ] Add chunk metadata:
  - `chunk_id`, `url`, `title`, `section_type`, `function_name` (if detectable)
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

### 2) Prompting + Generation

- [ ] Implement prompt builder with strict grounding instructions.
- [ ] Require output contract:
  - `query`
  - `explanation`
  - `assumptions`
  - `missing_context`
  - `cited_chunks`
- [ ] Integrate OpenAI chat model call.

### 3) Validation Layer

- [ ] Add lightweight response checks:
  - non-empty query
  - output format valid
  - cited chunks present
  - flag unresolved placeholders
- [ ] Add warning path when context is insufficient.

### 4) UI

- [ ] Build Streamlit app for ask -> retrieve -> generate flow.
- [ ] Show generated query + explanation + assumptions.
- [ ] Show cited documentation chunks to user.

## Phase 3 — Logging, Evaluation, Iteration

### 1) Logging

- [ ] Add query logging sink (Google Sheets initially).
- [ ] Log fields:
  - `timestamp`, `session_id`, `question`
  - `retrieved_chunk_ids`, `generated_query`
  - `assumptions`, `missing_context`
  - `model`, `validation_status`

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
- [ ] Add syntax-aware validator (later stage).
- [ ] Consider fine-tuning only after enough high-quality logs.

## Environment Checklist

- [ ] `OPENAI_API_KEY` configured
- [ ] `GOOGLE_SHEETS_CREDENTIALS_JSON` configured
- [ ] `GOOGLE_SHEET_ID` configured

## Runbook (Current)

- [x] Scrape PQL docs:

```bash
python scripts/scrape_docs.py
```

- [ ] Build chunk dataset
- [ ] Build embeddings/vector store
- [ ] Launch runtime app

