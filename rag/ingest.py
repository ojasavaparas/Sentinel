"""Document chunking and embedding ingestion pipeline."""

# TODO: Implement ingestion pipeline
# - Read markdown files from runbooks/ directory
# - Chunk documents by section headers (## headings)
# - Generate embeddings via the embeddings module
# - Upsert chunks into ChromaDB with metadata (source file, section title)
# - CLI entrypoint: python -m rag.ingest
