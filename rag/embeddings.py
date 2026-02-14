"""Embedding model wrapper using sentence-transformers (singleton pattern)."""

from __future__ import annotations

from sentence_transformers import SentenceTransformer

_MODEL_NAME = "all-MiniLM-L6-v2"
_instance: EmbeddingModel | None = None


class EmbeddingModel:
    """Wraps sentence-transformers to generate text embeddings."""

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        embeddings = self._model.encode(texts, show_progress_bar=False)
        return [e.tolist() for e in embeddings]


def get_embedding_model() -> EmbeddingModel:
    """Return a singleton EmbeddingModel instance (loads model once)."""
    global _instance
    if _instance is None:
        _instance = EmbeddingModel()
    return _instance
