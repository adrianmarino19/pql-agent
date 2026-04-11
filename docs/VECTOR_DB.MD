# Vector Store Notes

The local vector store uses Chroma persisted at `data/chroma/` with the
collection name `pql_docs`.

## Stored Data

Each chunk is upserted with:

- `id`: `chunk_id`
- `document`: normalized chunk text used for retrieval
- `embedding`: OpenAI `text-embedding-3-small` vector
- `metadata`:
  - `chunk_id`
  - `url`
  - `title`
  - `term_name`
  - `chunk_type`
  - `example_index`
  - `word_count`
  - `token_count`

## `term_name` Semantics

`term_name` is the canonical named PQL term represented by the page when it can
be derived reliably.

Population rule:

1. Extract the term from the `Syntax` block when possible.
2. If no usable syntax term exists, fall back to the page title only when the
   title matches a strict PQL-style pattern such as `MATCH_PROCESS_REGEX` or
   `STRING`.
3. Otherwise leave `term_name` empty.

This field is intended for future exact-match retrieval and lightweight
validation. It is broader than `function_name`, because it can also cover
datatypes and other named PQL constructs.

## Retrieval Use

The current store supports dense semantic retrieval over chunk embeddings.
Runtime retrieval can later combine:

- dense similarity on `document`
- exact filtering or boosting on `term_name`
- chunk-type-aware ranking using `chunk_type`
