# ADR-002: ChromaDB over Pinecone

## Status
Accepted

## Context
We need a vector database for RAG over operational runbooks. Options: ChromaDB (local), Pinecone (managed cloud), Weaviate, Qdrant.

## Decision
Use ChromaDB for vector storage.

## Rationale
- Runs locally with no external service dependency
- Simple Python API, easy to embed in the application
- Persistent storage to disk — survives restarts
- Zero cost for development and testing
- Sufficient for our runbook corpus size (hundreds of documents, not millions)

## Consequences
- Not suitable for massive scale (fine for operational runbooks)
- Migration to a managed solution (Pinecone, Qdrant Cloud) is straightforward if needed
