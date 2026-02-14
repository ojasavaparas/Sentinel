"""Vector search engine — queries ChromaDB for relevant runbook chunks."""

from __future__ import annotations

import os
from typing import Literal

import chromadb
import structlog
from pydantic import BaseModel, Field

from rag.embeddings import get_embedding_model
from rag.ingest import COLLECTION_NAME

logger = structlog.get_logger()


class RAGResult(BaseModel):
    """A single search result from the runbook vector store."""

    content: str
    source_file: str
    title: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    chunk_index: int
    confidence: Literal["high", "medium", "low"]


def _classify_confidence(score: float) -> Literal["high", "medium", "low"]:
    if score > 0.7:
        return "high"
    elif score >= 0.4:
        return "medium"
    return "low"


class RAGEngine:
    """Search engine over operational runbooks stored in ChromaDB."""

    def __init__(self, chroma_persist_dir: str | None = None) -> None:
        persist_dir = chroma_persist_dir or os.environ.get("CHROMA_PERSIST_DIR", "./chroma_data")
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._embedding_model = get_embedding_model()
        try:
            self._collection = self._client.get_collection(name=COLLECTION_NAME)
        except Exception:
            self._collection = None

    async def search(self, query: str, top_k: int = 3) -> list[RAGResult]:
        """Search runbooks for chunks relevant to the query."""
        if self._collection is None or self._collection.count() == 0:
            logger.warning("rag_search_empty_collection", query=query)
            return []

        query_embedding = self._embedding_model.embed([query])[0]

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self._collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        rag_results: list[RAGResult] = []
        documents = results["documents"][0] if results["documents"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []

        for doc, meta, distance in zip(documents, metadatas, distances):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity: 1 - (distance / 2)
            similarity = 1.0 - (distance / 2.0)
            confidence = _classify_confidence(similarity)

            rag_results.append(
                RAGResult(
                    content=doc,
                    source_file=meta["source_file"],
                    title=meta["title"],
                    similarity_score=round(similarity, 4),
                    chunk_index=int(meta["chunk_index"]),
                    confidence=confidence,
                )
            )

        top_score = rag_results[0].similarity_score if rag_results else 0.0
        logger.info(
            "rag_search",
            query=query,
            num_results=len(rag_results),
            top_score=top_score,
        )

        return rag_results
