import chromadb
from chromadb.errors import NotFoundError

from pql_agent.config import CHROMA_PATH, COLLECTION_NAME


def collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        return client.get_collection(COLLECTION_NAME)
    except (NotFoundError, ValueError) as exc:
        raise RuntimeError(
            f"Chroma collection '{COLLECTION_NAME}' was not found at '{CHROMA_PATH}'. "
            "Run `uv run pql-agent pipeline` first."
        ) from exc

