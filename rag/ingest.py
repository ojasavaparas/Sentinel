"""Document chunking and embedding ingestion pipeline for runbooks."""

from __future__ import annotations

import os
from pathlib import Path

import chromadb

from rag.embeddings import get_embedding_model

CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
COLLECTION_NAME = "runbooks"


def _extract_title(content: str) -> str:
    """Extract the markdown H1 title from document content."""
    for line in content.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return "Untitled"


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks of approximately chunk_size characters."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    return chunks


def ingest_runbooks(
    runbook_dir: str = "runbooks",
    chroma_persist_dir: str | None = None,
) -> None:
    """Read, chunk, embed, and store runbook documents in ChromaDB."""
    chroma_persist_dir = chroma_persist_dir or os.environ.get("CHROMA_PERSIST_DIR", "./chroma_data")
    runbook_path = Path(runbook_dir)

    if not runbook_path.exists():
        print(f"Runbook directory not found: {runbook_path}")
        return

    md_files = sorted(runbook_path.glob("*.md"))
    if not md_files:
        print("No markdown files found in runbooks/")
        return

    print(f"Found {len(md_files)} runbook files")

    all_chunks: list[str] = []
    all_metadatas: list[dict[str, str | int]] = []
    all_ids: list[str] = []

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        title = _extract_title(content)
        chunks = _chunk_text(content)

        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            all_metadatas.append({
                "source_file": md_file.name,
                "title": title,
                "chunk_index": i,
            })
            all_ids.append(f"{md_file.stem}__chunk_{i}")

    print(f"Created {len(all_chunks)} chunks from {len(md_files)} documents")

    print("Generating embeddings...")
    model = get_embedding_model()
    embeddings = model.embed(all_chunks)

    client = chromadb.PersistentClient(path=chroma_persist_dir)
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    collection.add(
        ids=all_ids,
        documents=all_chunks,
        embeddings=embeddings,  # type: ignore[arg-type]
        metadatas=all_metadatas,  # type: ignore[arg-type]
    )

    print(f"Stored {collection.count()} chunks in ChromaDB collection '{COLLECTION_NAME}'")
    print(f"Persist directory: {chroma_persist_dir}")


if __name__ == "__main__":
    ingest_runbooks()
