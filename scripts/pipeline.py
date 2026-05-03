import json
import sys
import time
from pathlib import Path

import chromadb

sys.path.insert(0, str(Path(__file__).parent))
from chunk import build_pql_dict, chunk_page
from embed import embed_chunks

JSONL_PATH = "data/scrape/pql_docs.jsonl"
CHROMA_PATH = "data/chroma"
COLLECTION_NAME = "pql_docs"
UPSERT_BATCH = 100


def load_pages(jsonl_path: str) -> list[dict]:
    pages = []
    with open(jsonl_path) as f:
        for line in f:
            doc = json.loads(line)
            if doc.get("status_code") == 200:
                pages.append(doc)
    return pages


def main() -> None:
    t0 = time.time()

    print("Loading pages...")
    pages = load_pages(JSONL_PATH)
    print(f"  {len(pages)} pages")

    print("Building PQL dictionary...")
    pql_dict = build_pql_dict(JSONL_PATH)
    print(f"  {len(pql_dict)} identifiers")

    print("Chunking...")
    all_chunks: list[dict] = []
    for doc in pages:
        all_chunks.extend(chunk_page(doc, pql_dict))

    type_counts: dict[str, int] = {}
    for c in all_chunks:
        type_counts[c["chunk_type"]] = type_counts.get(c["chunk_type"], 0) + 1
    print(f"  {len(all_chunks)} chunks total: {type_counts}")

    print("Embedding...")
    vectors = embed_chunks(all_chunks)
    print(f"  {len(vectors)} vectors")

    print("Rebuilding Chroma collection...")
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        client.delete_collection(COLLECTION_NAME)
    except ValueError:
        pass

    collection = client.get_or_create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [c["chunk_id"] for c in all_chunks]
    documents = [c["text"] for c in all_chunks]
    metadatas = [
        {k: (v if v is not None else "") for k, v in c.items() if k != "text"}
        for c in all_chunks
    ]

    for i in range(0, len(ids), UPSERT_BATCH):
        s = slice(i, i + UPSERT_BATCH)
        collection.upsert(
            ids=ids[s],
            documents=documents[s],
            embeddings=vectors[s],
            metadatas=metadatas[s],
        )

    elapsed = time.time() - t0
    print(f"Done. {collection.count()} chunks in '{COLLECTION_NAME}'. ({elapsed:.1f}s)")


if __name__ == "__main__":
    main()
