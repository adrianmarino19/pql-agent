# PQL Coding Assistant — Architecture

A RAG-powered coding assistant that answers natural language questions about PQL (Celonis Process Query Language) and generates valid PQL queries from them.
Many parts of the architecture remain to be discussed (like the frontend). Nonetheless, Phase 1 seems to be settled.

Validation: I built a custom GPT before, and it got 900 chats.

---

## Overview

Users ask questions in plain English. The system retrieves the relevant PQL documentation chunks, injects them into a prompt, and returns a working PQL query via GPT-4o. No PQL knowledge required from the user.

---

## Two Phases

### Phase 1 — Ingestion (run once)

Processes the raw PQL documentation into a searchable vector store.

```
PQL docs (local files)
        │
        ▼
   Chunker
   split by function / section
        │
        ▼
   Embeddings
   OpenAI text-embedding-3-small
        │
        ▼
   Chroma (local)
   vector store — persisted to disk
```

This phase runs once. Re-run only if the documentation is updated.

### Phase 2 — Runtime (per query)

Handles every user query end-to-end.

```
User types question
        │
        ▼
   Streamlit UI
   (deployed on Streamlit Cloud)
        │
        ▼
   Retriever
   embeds query → top-k chunk lookup in Chroma
        │
        ▼
   Prompt Builder
   assembles: retrieved chunks + user question
        │
        ▼
   GPT-4o
   generates PQL query
        │
        ▼
   Streamlit UI
   displays query to user
        │
        ▼
   Query Log
   appends question + generated query to Google Sheet
```

---

## Stack

| Component | Technology | Notes |
|---|---|---|
| Frontend | Streamlit | Deployed on Streamlit Cloud (free tier) |
| Vector store | Chroma | Local, persisted to disk |
| Embeddings | OpenAI `text-embedding-3-small` | Cheap, fast, good enough for v1 |
| LLM | GPT-4o | Via OpenAI API |
| Query log | Google Sheets | Via gspread — tracks all user queries |
| Docs | Local files | PQL documentation, pre-downloaded |

---

## Repository Structure

```
pql-assistant/
├── ingest/
│   ├── chunk.py          # splits docs by function/section
│   ├── embed.py          # embeds chunks, writes to Chroma
│   └── run_ingestion.py  # entry point: run once
├── app/
│   ├── retriever.py      # query embedding + Chroma lookup
│   ├── prompt.py         # assembles prompt from chunks + question
│   ├── logger.py         # writes to Google Sheet
│   └── main.py           # Streamlit app entry point
├── data/
│   └── docs/             # raw PQL documentation files
├── chroma_store/         # persisted vector DB (gitignored)
├── .env                  # API keys (gitignored)
├── requirements.txt
└── ARCHITECTURE.md
```

---

## Chunking Strategy

Documentation is chunked **by function or section**, not by page or fixed token count. This ensures that when a user asks about a specific PQL function, the full definition — including syntax, parameters, and examples — is retrieved as a single unit.

Each chunk includes:
- Function name
- Syntax
- Description
- Parameters
- Usage examples

---

## Prompt Structure

```
You are a PQL coding assistant. PQL (Process Query Language) is Celonis's proprietary query language.

Use only the documentation below to answer. Do not invent syntax.

--- DOCUMENTATION ---
{retrieved_chunks}
--- END DOCUMENTATION ---

User question: {user_question}

Return a PQL query that answers the question. Include a brief explanation of what each part does.
```

---

## Query Log Schema

Every query is logged to a Google Sheet with the following columns:

| Column | Description |
|---|---|
| `timestamp` | UTC datetime of the query |
| `question` | Raw user question |
| `retrieved_chunks` | IDs of chunks used in the prompt |
| `generated_query` | PQL query returned by GPT-4o |
| `session_id` | Anonymous session identifier |

This log serves as the v2 eval set and eventual fine-tuning dataset.

---

## v1 Scope (ship fast)

- [x] Ingestion pipeline — chunk, embed, store
- [x] Retriever — top-k similarity search
- [x] Prompt builder — inject chunks + question
- [x] GPT-4o integration
- [x] Streamlit UI
- [x] Streamlit Cloud deployment
- [x] Query logging to Google Sheet

## v2 Roadmap (after real usage data)

- [ ] Evaluate retrieval quality against logged queries
- [ ] Improve chunking strategy based on failure cases
- [ ] Add query validation (syntax check)
- [ ] Add few-shot examples based on most common query patterns
- [ ] Explore fine-tuning on logged query/answer pairs

---

## Environment Variables

```
OPENAI_API_KEY=
GOOGLE_SHEETS_CREDENTIALS_JSON=
GOOGLE_SHEET_ID=
```

---

## Running Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run ingestion (once)
python ingest/run_ingestion.py

# 3. Start the app
streamlit run app/main.py
```
