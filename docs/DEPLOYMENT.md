# Deployment — Streamlit Community Cloud

## Prereqs

- Repo on GitHub (public or private; Streamlit Cloud supports both).
- `pyproject.toml` lists `streamlit`, `chromadb`, `openai`, `python-dotenv`.
- `data/chroma/` committed to the repo. ~4MB. This is the cold-start vector store; rebuilding on boot is too slow.

## Streamlit Cloud config

- App entrypoint: `app/streamlit_app.py`.
- Python version: 3.11 (matches local).
- Secrets (set via Streamlit Cloud UI):
  - `OPENAI_API_KEY = "sk-..."`

## Env handling

`load_dotenv()` stays in `answer.py` for local dev. On Streamlit Cloud, `st.secrets["OPENAI_API_KEY"]` is read at app startup and exported into `os.environ` so existing OpenAI client init works unchanged.

## Soft throttle

Implemented in the UI (see `CHAT_UI.md`). No server-side rate limiting; this is a goodwill demo URL, not a public service.

## Updating the deployment

- Add docs / change chunking → run `uv run python scripts/pipeline.py` locally → commit `data/chroma/` → push → Streamlit Cloud auto-redeploys.

## Risks / known gaps

- The Chroma DB in git grows over time. Acceptable until it crosses ~50MB; revisit then.
- Cold-start container restarts re-read the committed Chroma; no rebuild needed.
- If the OpenAI key is leaked via misconfigured secrets, rotate immediately.
