import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pql_agent.retrieval.embeddings import embed_chunks

__all__ = ["embed_chunks"]

