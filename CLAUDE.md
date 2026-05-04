# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PQL Agent is a retrieval-augmented generation (RAG) assistant that converts natural language into grounded PQL (Process Query Language) queries using official Celonis documentation as its source of truth. The system prioritizes groundedness and explicit uncertainty over fluent output.

## Development Setup

- Python 3.11, managed with `uv`
- Install dependencies: `uv sync`
- Run the main entry point: `uv run python main.py`

## Key Commands

```bash
# Generate grounded PQL from a natural-language request
uv run python main.py ask "count cases where activity A happened before activity B"

# Inspect retrieval only
uv run python main.py retrieve "MATCH_PROCESS_REGEX" --top-k 3

# Scrape PQL docs (outputs JSONL to data/scrape/pql_docs.jsonl)
uv run python scripts/scrape_docs.py

# Scrape with options
uv run python scripts/scrape_docs.py --out data/scrape/pql_docs.jsonl --workers 8 --delay 0.1 --timeout 20 --max-pages 10
```

## Architecture

The system has three planned loops (only ingestion phase 1 is implemented):

1. **Ingestion loop**: scrape docs -> chunk -> embed -> vector store (ChromaDB)
2. **Runtime loop**: user query -> retrieve chunks -> prompt LLM -> validate -> respond
3. **Feedback loop**: log outcomes -> evaluate -> improve

### Current State

- `scripts/scrape_docs.py` — Complete. Parallel scraper that discovers PQL pages from the Celonis docs sidebar, fetches them with retry/backoff, extracts clean text, and writes JSONL.
- `scripts/chunk.py` — Complete. Builds PQL-aware chunks with `term_name`, `chunk_type`, and stable chunk IDs.
- `scripts/embed.py` and `scripts/pipeline.py` — Complete. Embed chunks with OpenAI and persist them in Chroma.
- `scripts/retrieve.py` — Complete. Retrieves top-k chunks with dense search and exact-term boosting.
- `scripts/answer.py` — Initial runtime. Retrieves chunks, builds a grounded prompt, calls the OpenAI chat model, validates the structured response, and logs JSONL records.
- `main.py` — CLI entry point with `retrieve` and `ask` subcommands.

### Planned Structure (from docs/ARCHITECTURE.md)

Code will be organized under `src/pql_agent/` with separate packages for `ingest/`, `runtime/`, `app/`, and `logging/`. The runtime must return structured output: `query`, `explanation`, `cited_chunks`. Chunk metadata now includes `term_name` for named PQL constructs when derivable from syntax or a strict title heuristic.

### Design Constraints

- The LLM must use only retrieved documentation context — never invent PQL syntax.
- When docs are insufficient, the system must explicitly state what is missing rather than guessing.
- Retrieval, generation, and validation must be separate and independently observable.

## Dependencies

- `beautifulsoup4` — HTML parsing for scraper
- `chromadb` — Vector store for embeddings
- `requests` — HTTP client for scraping
