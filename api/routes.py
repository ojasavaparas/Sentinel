"""API endpoints for incident analysis and system status."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query
from prometheus_client import generate_latest
from starlette.responses import Response as StarletteResponse

from agent.models import Alert, IncidentReport
from api.deps import get_analyzer, get_incident_store, get_rag_engine

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1")
metrics_router = APIRouter()


# --- Incident Analysis ---


@router.post("/analyze", response_model=IncidentReport)
async def analyze_incident(alert: Alert) -> IncidentReport:
    """Run full incident analysis pipeline on an alert."""
    from monitoring.metrics import sentinel_active_analyses

    analyzer = get_analyzer()
    store = get_incident_store()

    sentinel_active_analyses.inc()
    try:
        report = await analyzer.analyze(alert)
        store[report.incident_id] = report
        logger.info("api_analyze_complete", incident_id=report.incident_id)
        return report
    finally:
        sentinel_active_analyses.dec()


@router.get("/incidents")
async def list_incidents(
    limit: int = Query(default=20, ge=1, le=100),
    severity: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """List recent incident analyses."""
    store = get_incident_store()
    incidents = list(store.values())

    if severity:
        incidents = [i for i in incidents if i.alert.severity == severity]

    # Sort by most recent first (based on alert timestamp)
    incidents.sort(key=lambda x: x.alert.timestamp, reverse=True)
    incidents = incidents[:limit]

    return [
        {
            "incident_id": i.incident_id,
            "service": i.alert.service,
            "severity": i.alert.severity,
            "summary": i.summary,
            "confidence_score": i.confidence_score,
            "requires_human_approval": i.requires_human_approval,
            "duration_seconds": i.duration_seconds,
            "total_cost_usd": i.total_cost_usd,
            "timestamp": i.alert.timestamp.isoformat(),
        }
        for i in incidents
    ]


@router.get("/incidents/{incident_id}", response_model=IncidentReport)
async def get_incident(incident_id: str) -> IncidentReport:
    """Get a specific incident report with full agent trace."""
    store = get_incident_store()
    if incident_id not in store:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return store[incident_id]


@router.get("/incidents/{incident_id}/trace")
async def get_incident_trace(incident_id: str) -> list[dict[str, Any]]:
    """Get just the decision trace for an incident."""
    store = get_incident_store()
    if incident_id not in store:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

    report = store[incident_id]
    return [
        {
            "agent_name": step.agent_name,
            "action": step.action,
            "reasoning": step.reasoning,
            "tool_calls": [
                {
                    "tool_name": tc.tool_name,
                    "arguments": tc.arguments,
                    "latency_ms": tc.latency_ms,
                }
                for tc in step.tool_calls
            ],
            "tokens_used": step.tokens_used,
            "cost_usd": step.cost_usd,
            "timestamp": step.timestamp.isoformat(),
        }
        for step in report.agent_trace
    ]


# --- Runbook Search ---


@router.post("/runbooks/search")
async def search_runbooks(body: dict[str, Any]) -> dict[str, Any]:
    """Search runbooks via RAG."""
    from monitoring.metrics import sentinel_rag_queries_total

    query = body.get("query", "")
    top_k = body.get("top_k", 3)

    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    engine = get_rag_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="RAG engine not initialized")

    sentinel_rag_queries_total.inc()
    results = await engine.search(query, top_k=top_k)

    return {
        "query": query,
        "results": [
            {
                "content": r.content,
                "source_file": r.source_file,
                "title": r.title,
                "similarity_score": r.similarity_score,
                "confidence": r.confidence,
                "chunk_index": r.chunk_index,
            }
            for r in results
        ],
        "num_results": len(results),
    }


# --- Health ---


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Service health check."""
    engine = get_rag_engine()
    chroma_ok = engine is not None and engine._collection is not None

    return {
        "status": "healthy",
        "chroma_db": "connected" if chroma_ok else "disconnected",
        "llm_provider": "configured",
        "runbooks_indexed": chroma_ok,
    }


# --- Prometheus Metrics ---


@metrics_router.get("/metrics")
async def prometheus_metrics() -> StarletteResponse:
    """Expose Prometheus metrics."""
    return StarletteResponse(
        content=generate_latest(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
