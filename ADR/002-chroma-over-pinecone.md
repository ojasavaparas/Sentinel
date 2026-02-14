# ADR-002: ChromaDB over Pinecone

## Status
Accepted

## Context
Sentinel's RAG engine needs a vector database to store and retrieve operational runbook embeddings. When an agent searches for "database connection pool troubleshooting," the system must return the most relevant runbook chunks ranked by semantic similarity. The candidate vector stores were: ChromaDB (local, embedded), Pinecone (managed cloud), Weaviate (self-hosted or cloud), and Qdrant (self-hosted or cloud).

Our runbook corpus is small — tens of documents producing hundreds of chunks. The system must work offline for local development and testing without requiring external API keys or network access beyond the LLM API itself.

## Decision
Use ChromaDB as the vector database with local persistent storage and `sentence-transformers` for embedding generation.

## Reasoning
ChromaDB runs as an embedded Python library with no separate server process. It persists collections to disk and survives application restarts. The Python API is minimal — `add`, `query`, `get` — and integrates naturally with our existing Pydantic-based architecture. For our runbook corpus size (hundreds of chunks, not millions), ChromaDB's retrieval performance is effectively instant.

Using `sentence-transformers` for embeddings means the entire RAG pipeline runs locally with zero external dependencies beyond the Anthropic API. This eliminates a class of failure modes (embedding API outages, rate limits, additional API keys) and keeps the development loop fast.

## Trade-offs
- **Not production-scale**: ChromaDB is not designed for millions of vectors or multi-tenant workloads. If Sentinel were deployed for a large organization with thousands of runbooks, a managed solution like Pinecone or Qdrant Cloud would be necessary.
- **No built-in replication**: Single-node storage means no high availability. Acceptable for a development/demo system.
- **Embedding model runs locally**: Requires ~500MB for the sentence-transformer model on first download. Adds to container image size.

## Consequences
- Zero cost for vector storage in development, testing, and demos.
- `make ingest` populates the collection from markdown files in seconds.
- The `RAGEngine` interface is abstract enough that swapping to Pinecone or Qdrant requires only changing the engine implementation — the tool interface and agent prompts remain unchanged.
- Docker Compose includes a ChromaDB service for the full-stack deployment, exposing it on port 8001.
