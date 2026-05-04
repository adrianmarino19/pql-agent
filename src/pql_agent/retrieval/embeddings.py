import tiktoken
from dotenv import load_dotenv
from openai import OpenAI

from pql_agent.config import EMBEDDING_MODEL

MAX_EMBED_TOKENS = 8191


def _truncate(text: str) -> str:
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    if len(tokens) <= MAX_EMBED_TOKENS:
        return text
    return enc.decode(tokens[:MAX_EMBED_TOKENS])


def embed_query(query: str, model: str = EMBEDDING_MODEL) -> list[float]:
    load_dotenv()
    client = OpenAI()
    response = client.embeddings.create(model=model, input=query)
    return response.data[0].embedding


def embed_chunks(chunks: list[dict], model: str = EMBEDDING_MODEL) -> list[list[float]]:
    load_dotenv()
    client = OpenAI()
    texts = [_truncate(c["text"]) for c in chunks]
    vectors: list[list[float]] = []
    batch_size = 100

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(model=model, input=batch)
        batch_vectors = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        vectors.extend(batch_vectors)

    return vectors

