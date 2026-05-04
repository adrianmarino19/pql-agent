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
- [x] **Ingestion pipeline complete** (chunk + embed + vector store).
- [x] Runtime CLI implemented for retrieval + prompt + generation + validation + local logging.

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
  - [x] Three-tier logic: Tier 1/2 (≤2048 tokens) → single `full` chunk; Tier 3 (>2048) → split on sequential `[n]` markers.
  - [x] Separate `description_syntax` and `example` chunks for Tier 3.
  - [x] PQL dictionary normalization: `MATCH_PROCESS_REGEX` → `match process regex` before embedding (improves tokenization).
  - [x] Concept pages (no `Syntax` block) → single `chunk_type: concept`.
  - [x] Sequential marker validation to skip false positives (`[1904]` inside example text).
  - [x] Chunk metadata: `chunk_id` (SHA256 hash of url+chunk_type+example_index), `url`, `title`, `term_name`, `chunk_type`, `example_index`, `word_count`, `token_count`, `text`.
  - Result: **598 chunks** from 291 pages (65 concept, 188 full, 38 description_syntax, 307 example).

### 5) Embedding + Vector Store

- [x] **Add embedding script** (`scripts/embed.py`):
  - [x] Batch OpenAI API calls (batches of 100 chunks).
  - [x] Model: `text-embedding-3-small` (1536 dimensions).
  - [x] Token truncation at 8191 (API limit); 1 chunk exceeds this and will be truncated.
- [x] **Orchestrate pipeline** (`scripts/pipeline.py`):
  - [x] Load JSONL → build PQL dict → chunk → embed → upsert into Chroma at `data/chroma/`.
  - [x] Chroma collection: `pql_docs`, cosine similarity, local persistent store.
- [ ] Add idempotent re-run behavior (skip unchanged by content hash).
- [x] Add quick retrieval smoke test (`top-k` by sample query).

## Phase 2 — Runtime Assistant

### 1) Retrieval

- [x] Implement retriever module: query embed -> Chroma similarity search.
- [x] Return top-k chunks + chunk metadata.
- [ ] Add score threshold.
- [x] Add keyword fallback for exact PQL term matches (via Chroma `where` filters on `term_name` metadata).

### 2) CLI runtime (before UI)

- [x] Build CLI script: takes a natural-language question, prints structured response.
- [x] Use CLI to iterate on prompt and retrieval quality before building UI.

### 3) Prompting + Generation

- [x] Implement prompt builder with strict grounding instructions.
- [x] Require output contract:
  - `query`
  - `explanation`
  - `cited_chunks`
- [x] Integrate OpenAI chat model call.

### 4) Schema Context Input

- [x] Allow user to provide table/column schema as input (e.g. paste schema text).
- [x] Inject schema context into prompt alongside retrieved chunks.
- [x] When schema is missing and required, state that clearly in the explanation.

### 5) Validation Layer

- [x] Add lightweight response checks:
  - non-empty query
  - output format valid
  - cited chunks present
  - referenced functions appear in retrieved docs
  - flag unresolved placeholders
- [x] Add warning path for validation issues.

### 6) UI

- [ ] Build Streamlit app for ask -> retrieve -> generate flow.
- [ ] Show generated query + explanation.
- [ ] Show cited documentation chunks to user.
- [ ] v1 frontend design and execution split across per-workstream docs:
  - `V1_OVERVIEW.md`
  - `AGENTIC_RUNTIME.md`
  - `CHAT_UI.md`
  - `LOGGING_AND_FEEDBACK.md`
  - `DEPLOYMENT.md`
  - `ITERATION_WORKFLOW.md`

## Phase 3 — Logging, Evaluation, Iteration

### 1) Logging

- [x] Add query logging sink (local JSONL or SQLite).
- [x] Log fields:
  - `timestamp`, `session_id`, `question`
  - `retrieved_chunk_ids`, `retrieval_titles`, `generated_query`
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
3. Chunk pages using the three-tier strategy → 598 chunks
4. Embed with OpenAI `text-embedding-3-small`
5. Upsert into Chroma at `data/chroma/pql_docs`
6. Print summary: elapsed time, total chunks stored

### Ask PQL assistant
```bash
uv run python main.py ask "count cases where activity A happened before activity B"
```

This will:
1. Retrieve the top documentation chunks from Chroma
2. Build a strict grounded prompt
3. Generate structured JSON with `query`, `explanation`, and `cited_chunks`
4. Run lightweight validation
5. Append a local JSONL log entry at `data/logs/queries.jsonl`

**Next steps:**
- [ ] Add score threshold tuning to retrieval
- [ ] Launch Streamlit app
