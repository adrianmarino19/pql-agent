# PQL Agent Architecture

`pql-agent` is a grounded assistant that helps users write PQL from natural-language requests using the official PQL documentation as its source of truth.

The core product idea is sound. This is a narrow domain, the docs are authoritative, and user intent is usually "translate business question into valid syntax," which fits retrieval-augmented generation well.

The main architectural risk is not retrieval itself. It is producing confident but invalid queries when the docs are incomplete, the user's schema context is missing, or multiple PQL constructs could plausibly fit. The system should therefore optimize for groundedness and explicit uncertainty, not just fluent output.

## Product Goal

Given a user request such as "count cases where activity A happened before activity B", the agent should:

1. Retrieve the most relevant PQL documentation sections.
2. Produce a syntactically plausible PQL query grounded in those sections.
3. Explain the query in plain English.
4. Call out missing business context when the request cannot be fully resolved from documentation alone.

This is more useful than a generic chatbot because it is:

- constrained to one language,
- backed by the actual docs,
- optimized for query authoring rather than open-ended Q&A.

## Design Principles

- Grounded first: use retrieved documentation as the source of truth.
- Do not hallucinate: if the docs do not support a construct, say so.
- Separate retrieval, generation, and validation: they should be observable and independently improvable.
- Log enough metadata to evaluate failures later.
- Ship a small v1, but leave room for a stricter validation layer.

## System Overview

There are three loops in the system:

1. Ingestion loop: transform raw docs into a searchable knowledge base.
2. Runtime loop: answer user requests with retrieval + generation + validation.
3. Feedback loop: log outcomes and use them to improve prompts, chunking, and tests.

## Phase 1: Ingestion

The ingestion pipeline converts raw PQL documentation into chunks that are semantically meaningful for retrieval.

```text
PQL docs
    |
    v
Document parser
extracts functions, sections, examples, notes
    |
    v
Chunker
chunks by function / concept / syntax block
    |
    v
Metadata enricher
adds title, function name, category, source URL/path, version
    |
    v
Embeddings
    |
    v
Vector store
```

### Recommended chunk shape

Chunk by function or concept, not by fixed token window alone.

Each chunk should carry metadata such as:

- `chunk_id`
- `title`
- `function_name` if applicable
- `category`
- `source_path` or canonical doc URL
- `doc_version`
- `section_type` such as syntax, parameter, example, note

This matters because retrieval quality will improve if the prompt can distinguish "syntax definition" from "example" from "edge-case note".

## Phase 2: Runtime

At runtime, the system should not be just "retrieve docs, ask model, print answer". It should have an explicit validation step.

```text
User request
    |
    v
UI / API
    |
    v
Retriever
top-k chunks + optional reranking
    |
    v
Prompt builder
inject docs + output contract
    |
    v
LLM
draft query + explanation + assumptions
    |
    v
Validator
basic syntax / structure / groundedness checks
    |
    v
Response formatter
    |
    v
User + query log
```

### Runtime contract

The model should return structured output with:

- `query`
- `explanation`
- `assumptions`
- `missing_context`
- `cited_chunks`

This is better than a single free-form answer because it forces the model to separate what it knows from what it is assuming.

## Retrieval Strategy

The retrieval strategy is the right starting point, but I would make it slightly stricter:

- Start with semantic search over doc chunks.
- Retrieve a small number of chunks with high precision.
- Prefer chunks containing syntax and examples over purely descriptive prose.
- Consider reranking later if initial retrieval feels noisy.

For v1, a plain vector search is enough. For v2, hybrid retrieval is worth considering:

- dense retrieval for semantic match,
- keyword match for exact function names,
- lightweight reranking for final ordering.

PQL queries often hinge on exact operators and function signatures, so keyword sensitivity will matter more here than in a generic docs bot.

## Prompting Strategy

The current concept is correct, but the prompt should impose harder boundaries.

Recommended prompt behavior:

- Use only the supplied documentation context.
- Do not invent functions or arguments.
- If the question requires schema knowledge or business definitions not present in the docs, state the missing inputs explicitly.
- If multiple formulations are possible, give the safest one and name the assumption.
- Prefer short, valid output over clever output.

### Suggested response contract

```text
You are a PQL authoring assistant.

Use only the documentation context provided below.
If the documentation is insufficient, say exactly what is missing.
Do not invent PQL syntax, functions, or parameters.

Return:
1. A PQL query
2. A short explanation
3. Explicit assumptions
4. Missing context, if any
5. The chunk IDs you relied on
```

That one change alone will reduce ungrounded answers.

## Validation Layer

This is the biggest addition I would make to the architecture.

Even a lightweight validator will improve reliability a lot. v1 does not need a full PQL parser, but it should still check:

- whether the output is empty,
- whether referenced functions appear in retrieved docs,
- whether the response includes unresolved placeholders,
- whether the model admitted missing context,
- whether output format is valid.

Later, validation can evolve into:

- syntax-aware parsing,
- rule checks against known PQL function signatures,
- evaluation against curated gold examples.

## Logging and Evaluation

Logging to a Google Sheet is reasonable for a first pass, but the schema should capture enough signal to debug failures.

Recommended columns:

| Column | Description |
|---|---|
| `timestamp` | UTC timestamp |
| `session_id` | Anonymous session identifier |
| `question` | Raw user prompt |
| `retrieved_chunk_ids` | Chunk IDs used |
| `retrieval_titles` | Human-readable chunk titles |
| `generated_query` | Final query shown to user |
| `assumptions` | Assumptions surfaced by the model |
| `missing_context` | Missing schema/business context |
| `model` | Model used |
| `user_feedback` | Optional thumbs up/down later |
| `validation_status` | Passed / warned / failed |

This log is your evaluation dataset. Without retrieval metadata and validation outcome, it will be much harder to improve the system systematically.

## Repository Structure

The structure in this document should reflect a realistic near-term repo shape, not an already-finished one. A tighter layout would be:

```text
pql-agent/
├── docs/
│   └── ARCHITECTURE.md
├── src/
│   └── pql_agent/
│       ├── ingest/
│       │   ├── chunk.py
│       │   ├── embed.py
│       │   └── pipeline.py
│       ├── runtime/
│       │   ├── retriever.py
│       │   ├── prompt.py
│       │   ├── validator.py
│       │   └── generate.py
│       ├── app/
│       │   └── streamlit_app.py
│       └── logging/
│           └── query_logger.py
├── data/
│   └── docs/
├── tests/
├── pyproject.toml
└── README.md
```

That keeps ingestion, runtime, validation, and app concerns separated from the start.

## Recommended Stack

| Component | Recommendation | Notes |
|---|---|---|
| Frontend | Streamlit | Good for fast iteration |
| Vector store | Chroma | Fine for local-first v1 |
| Embeddings | Small OpenAI embedding model | Keep cost low in early iteration |
| LLM | A reliable general-purpose OpenAI model | Use one with strong instruction-following |
| Logging | Google Sheets initially | Replace later if evaluation volume grows |
| Docs source | Local docs plus source metadata | Preserve traceability |

I would avoid hard-coding a specific model name into the architecture unless you know you want to pin it operationally. That choice will change faster than the rest of the system design.

## v1 Scope

The right v1 is:

- ingest the docs,
- retrieve relevant chunks,
- generate grounded queries,
- return assumptions and missing context,
- log enough metadata to inspect failures,
- manually review outputs before claiming "valid PQL".

I would not define v1 success as "always returns a working query". I would define it as:

"Usually returns a useful first draft and clearly states when more context is needed."

That target is realistic and defensible.

## v2 Roadmap

After collecting real usage data, the next upgrades should be:

- retrieval evaluation on logged prompts,
- better chunking for edge-case functions,
- hybrid search,
- validator improvements,
- few-shot examples for recurring query types,
- a curated test set of natural-language request to expected PQL patterns,
- optional schema-aware prompting if users can provide table/column context.

## Final Take

The idea is good. It is focused, data-grounded, and much more credible than a generic "AI data copilot" pitch.

The edits I wanted to make were mostly about rigor:

- add a validation layer,
- force explicit assumptions and missing context,
- make logging useful for evaluation,
- avoid overclaiming correctness,
- align the proposed repo shape with where the project actually is.

If you want, I can take the next step and turn this architecture into an implementation plan with concrete modules, interfaces, and a first-pass build order.
