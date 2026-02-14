"""Tests for RAG engine and ingestion pipeline."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from rag.engine import RAGEngine
from rag.ingest import _chunk_text, _extract_title, ingest_runbooks


@pytest.fixture
def runbook_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with sample runbook files."""
    rb1 = tmp_path / "database-connection-pool-exhaustion.md"
    rb1.write_text(
        "# Database Connection Pool Exhaustion\n\n"
        "## Symptoms\n"
        "Connection pool utilization above 90%. Spike in database timeout errors. "
        "New connections being refused or queuing indefinitely. "
        "Service latency increases proportional to pool saturation.\n\n"
        "## Investigation Steps\n"
        "### 1. Check Pool Utilization Metrics\n"
        "Query the connection pool dashboard. Normal utilization should be 30-60%. "
        "Anything above 85% indicates exhaustion risk.\n\n"
        "### 2. Identify Long-Running Queries\n"
        "Check pg_stat_activity for queries running longer than 30 seconds. "
        "Kill any queries running longer than 5 minutes.\n"
    )

    rb2 = tmp_path / "high-latency-troubleshooting.md"
    rb2.write_text(
        "# High Latency Troubleshooting\n\n"
        "## Symptoms\n"
        "P99 latency exceeding normal baseline. Increased HTTP 504 errors. "
        "Upstream services reporting degraded performance.\n\n"
        "## Investigation Steps\n"
        "### 1. Check Recent Deployments\n"
        "If a deployment occurred within the last 60 minutes, it is the most likely cause. "
        "Proceed to rollback if correlation is strong.\n\n"
        "### 2. Verify Database Connection Pool\n"
        "If pool utilization exceeds 85%, the pool is near saturation.\n"
    )

    rb3 = tmp_path / "dns-resolution-failures.md"
    rb3.write_text(
        "# DNS Resolution Failure Troubleshooting\n\n"
        "## Symptoms\n"
        "Services logging name resolution errors. Intermittent connection failures. "
        "CoreDNS pods showing elevated error rates.\n\n"
        "## Steps\n"
        "Check CoreDNS health and verify resolv.conf configuration.\n"
    )

    return tmp_path


@pytest.fixture
def chroma_dir() -> Path:
    """Create a temporary ChromaDB directory."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def ingested_engine(runbook_dir: Path, chroma_dir: Path) -> RAGEngine:
    """Return a RAGEngine with ingested runbooks."""
    ingest_runbooks(
        runbook_dir=str(runbook_dir),
        chroma_persist_dir=str(chroma_dir),
    )
    return RAGEngine(chroma_persist_dir=str(chroma_dir))


def test_extract_title():
    assert _extract_title("# My Runbook\n\nContent") == "My Runbook"
    assert _extract_title("No heading here") == "Untitled"


def test_chunk_text_creates_overlapping_chunks():
    text = "A" * 1024
    chunks = _chunk_text(text, chunk_size=512, overlap=50)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 512


def test_ingestion_creates_correct_chunks(runbook_dir: Path, chroma_dir: Path):
    """Test that ingestion processes all documents and creates chunks."""
    ingest_runbooks(
        runbook_dir=str(runbook_dir),
        chroma_persist_dir=str(chroma_dir),
    )

    import chromadb

    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_collection("runbooks")

    # 3 documents should produce multiple chunks
    assert collection.count() > 3


@pytest.mark.asyncio
async def test_search_database_connection_pool(ingested_engine: RAGEngine):
    """Search for 'database connection pool' should return the DB runbook."""
    results = await ingested_engine.search("database connection pool exhaustion")

    assert len(results) > 0
    source_files = [r.source_file for r in results]
    assert "database-connection-pool-exhaustion.md" in source_files
    assert results[0].similarity_score > 0.4


@pytest.mark.asyncio
async def test_search_high_latency(ingested_engine: RAGEngine):
    """Search for 'high latency' should return the latency runbook."""
    results = await ingested_engine.search("high latency troubleshooting")

    assert len(results) > 0
    source_files = [r.source_file for r in results]
    assert "high-latency-troubleshooting.md" in source_files


@pytest.mark.asyncio
async def test_low_confidence_query(ingested_engine: RAGEngine):
    """A query unrelated to any runbook should return low similarity scores."""
    results = await ingested_engine.search("quantum computing algorithms")

    assert len(results) > 0
    # All results should have low or medium confidence for an unrelated query
    for result in results:
        assert result.similarity_score < 0.8


@pytest.mark.asyncio
async def test_empty_collection_returns_no_results(chroma_dir: Path):
    """Searching an empty collection should return an empty list."""
    engine = RAGEngine(chroma_persist_dir=str(chroma_dir))
    results = await engine.search("anything")
    assert results == []
