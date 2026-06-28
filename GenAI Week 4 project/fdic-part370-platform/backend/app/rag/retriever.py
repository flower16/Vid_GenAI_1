"""
LangChain RAG over the FDIC Part 370 corpus, backed by Pinecone.

Falls back to the in-code structured rule table (domain.orc.rules) when
Pinecone / embeddings are not configured, so the platform runs end-to-end in
local/dev without external services.
"""

from __future__ import annotations

import logging

from ..core.config import settings
from ..domain.constants import ORC
from ..domain.orc.rules import ORC_RULES, rule_text

logger = logging.getLogger(__name__)


class FDICRetriever:
    """Retrieve Part 370 rule context for an ORC + free-text query."""

    def __init__(self) -> None:
        self._vs = None
        if settings.pinecone_api_key and settings.openai_api_key:
            try:
                self._vs = self._init_pinecone()
            except Exception as exc:  # pragma: no cover - external dep
                logger.warning("Pinecone init failed, using local rules: %s", exc)

    def _init_pinecone(self):  # pragma: no cover - external dep
        from langchain_openai import OpenAIEmbeddings
        from langchain_pinecone import PineconeVectorStore

        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large", api_key=settings.openai_api_key
        )
        return PineconeVectorStore(
            index_name=settings.pinecone_index,
            embedding=embeddings,
            pinecone_api_key=settings.pinecone_api_key,
        )

    def retrieve(self, orc: ORC, query: str = "", k: int = 4) -> list[str]:
        """Return rule snippets most relevant to the ORC/query."""
        if self._vs is not None:  # pragma: no cover - external dep
            q = f"FDIC Part 370 ORC {orc.value} {query}".strip()
            docs = self._vs.similarity_search(q, k=k, filter={"orc": orc.value})
            if docs:
                return [d.page_content for d in docs]
        # Deterministic fallback
        return [rule_text(orc)]

    def applicable_rules(self, orc: ORC) -> dict:
        snippets = self.retrieve(orc)
        return {
            "orc": orc.value,
            "name": ORC_RULES[orc]["name"],
            "smdia": ORC_RULES[orc]["smdia"],
            "citation": ORC_RULES[orc]["citation"],
            "snippets": snippets,
        }


def seed_pinecone() -> int:  # pragma: no cover - external dep / one-off
    """Index the structured rule corpus into Pinecone. Returns doc count."""
    from langchain_core.documents import Document
    from langchain_openai import OpenAIEmbeddings
    from langchain_pinecone import PineconeVectorStore

    docs = [
        Document(page_content=rule_text(orc),
                 metadata={"orc": orc.value, "name": ORC_RULES[orc]["name"]})
        for orc in ORC
    ]
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large",
                                  api_key=settings.openai_api_key)
    PineconeVectorStore.from_documents(
        docs, embeddings, index_name=settings.pinecone_index,
        pinecone_api_key=settings.pinecone_api_key,
    )
    return len(docs)


retriever = FDICRetriever()
