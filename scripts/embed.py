import tiktoken
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
_client = OpenAI()
_enc = tiktoken.get_encoding("cl100k_base")
MAX_EMBED_TOKENS = 8191


def _truncate(text: str) -> str:
    tokens = _enc.encode(text)
    if len(tokens) <= MAX_EMBED_TOKENS:
        return text
    return _enc.decode(tokens[:MAX_EMBED_TOKENS])


def embed_chunks(chunks: list[dict], model: str = "text-embedding-3-small") -> list[list[float]]:
    texts = [_truncate(c["text"]) for c in chunks]
    vectors: list[list[float]] = []
    batch_size = 100

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = _client.embeddings.create(model=model, input=batch)
        batch_vectors = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        vectors.extend(batch_vectors)

    return vectors
