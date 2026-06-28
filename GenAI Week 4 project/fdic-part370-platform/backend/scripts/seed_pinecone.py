"""
Seed the Pinecone vector index with the FDIC Part 370 ORC rule corpus, so the
FDIC Rules Agent can retrieve rules via RAG instead of the in-code fallback.

Usage (from backend/):
    python scripts/seed_pinecone.py

Requires PINECONE_API_KEY and OPENAI_API_KEY (for embeddings) in backend/.env.
Creates the index if it doesn't exist (dimension 3072 for text-embedding-3-large).
"""

from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402

EMBED_DIM = 3072  # text-embedding-3-large


def ensure_index() -> None:  # pragma: no cover - external dep
    from pinecone import Pinecone, ServerlessSpec

    pc = Pinecone(api_key=settings.pinecone_api_key)
    existing = {i["name"] for i in pc.list_indexes()}
    if settings.pinecone_index in existing:
        print(f"Index '{settings.pinecone_index}' already exists.")
        return
    print(f"Creating index '{settings.pinecone_index}' (dim={EMBED_DIM}, cosine)...")
    pc.create_index(
        name=settings.pinecone_index,
        dimension=EMBED_DIM,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
    # wait until the index is ready
    for _ in range(30):
        if pc.describe_index(settings.pinecone_index).status.get("ready"):
            break
        time.sleep(2)
    print("Index ready.")


def main() -> int:
    missing = [k for k, v in (("PINECONE_API_KEY", settings.pinecone_api_key),
                              ("OPENAI_API_KEY", settings.openai_api_key)) if not v]
    if missing:
        print(f"Missing in backend/.env: {', '.join(missing)} — nothing to seed.")
        print("The platform still works: the FDIC Rules Agent falls back to the "
              "in-code rule corpus (domain/orc/rules.py) when Pinecone is absent.")
        return 1

    try:
        ensure_index()
        from app.rag.retriever import seed_pinecone
        count = seed_pinecone()
    except ImportError as exc:
        print(f"Missing dependency: {exc} (pip install -r requirements.txt)")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Pinecone seeding failed: {exc}")
        return 2

    print(f"\nIndexed {count} ORC rule documents into '{settings.pinecone_index}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
