# Iteration Workflow — "edit fast"

## Loop

1. Edit source: add/modify pages in `data/scrape/pql_docs.jsonl`, or change `scripts/chunk.py`.
2. Rebuild: `uv run python scripts/pipeline.py`.
3. Verify locally with `uv run streamlit run app/streamlit_app.py`.
4. Commit `data/chroma/` and any code changes; push.
5. Streamlit Cloud redeploys.

## Follow-up: idempotent pipeline re-run

Today `pipeline.py` re-embeds all 598 chunks every run. After heavy iteration this becomes painful (cost + ~30s per rebuild).

Add content-hash skipping:
- For each chunk, compute a hash over `(text, term_name, chunk_type, embedding_model)`.
- Look up the existing Chroma record by `chunk_id`. If the hash matches, skip embedding and upsert.
- If absent or mismatched, embed and upsert.

Files touched: `scripts/pipeline.py`, `scripts/embed.py`.

This is a quality-of-life follow-up, not a v1 blocker. Roadmap item already exists in `ROADMAP.md` (§5, "Add idempotent re-run behavior").
