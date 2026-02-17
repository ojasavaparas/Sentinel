"""FastAPI application — main entrypoint for the Sentinel API."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.responses import Response

from agent.core import IncidentAnalyzer
from agent.llm_client import create_client
from api.deps import (
    IncidentStore,
    get_incident_store,
    init_analyzer,
    init_incident_store,
    init_rag_engine,
)
from api.routes import metrics_router, router
from api.seed_data import get_seed_incidents
from rag.engine import RAGEngine
from rag.ingest import COLLECTION_NAME, ingest_runbooks

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
    """Startup and shutdown events."""
    # Configure structured logging before anything else
    from monitoring.logging import configure_logging

    configure_logging()

    logger.info("sentinel_starting")

    # Initialize RAG engine — ingest runbooks if collection is empty
    try:
        import os

        import chromadb

        persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_data")
        client = chromadb.PersistentClient(path=persist_dir)
        try:
            collection = client.get_collection(COLLECTION_NAME)
            if collection.count() == 0:
                raise ValueError("empty")
        except Exception:
            logger.info("ingesting_runbooks")
            ingest_runbooks()

        rag_engine = RAGEngine()
        init_rag_engine(rag_engine)
        logger.info("rag_engine_initialized")
    except Exception as e:
        logger.error("rag_init_failed", error=str(e))
        rag_engine = None

    # Initialize the incident analyzer
    llm_client = create_client()
    analyzer = IncidentAnalyzer(llm_client=llm_client, rag_engine=rag_engine)
    init_analyzer(analyzer)
    logger.info("analyzer_initialized")

    # Initialize incident store — DynamoDB in production, in-memory locally
    table_name = os.environ.get("DYNAMODB_TABLE_NAME")
    init_incident_store(IncidentStore(table_name=table_name))
    logger.info("incident_store_initialized", dynamo=table_name is not None)

    # Seed example incidents so the dashboard isn't empty
    store = get_incident_store()
    if not store:
        for incident in get_seed_incidents():
            store[incident.incident_id] = incident
        logger.info("seed_incidents_loaded", count=len(store))

    yield

    logger.info("sentinel_shutdown")


app = FastAPI(
    title="Sentinel",
    description="Multi-agent AI system for automated production incident analysis",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Map API paths to dashboard pages for browser redirects
_API_TO_PAGE = {
    "/api/v1/health": "health",
    "/api/v1/incidents": "incidents",
    "/api/v1/runbooks/search": "runbooks",
    "/metrics": "metrics",
}


# Request logging + browser redirect middleware
@app.middleware("http")
async def log_requests(request: Request, call_next: Any) -> Response:
    # Redirect browsers hitting API paths to the dashboard UI
    accept = request.headers.get("accept", "")
    path = request.url.path
    if (
        request.method == "GET"
        and "text/html" in accept
        and path in _API_TO_PAGE
    ):
        return RedirectResponse(url=f"/#{_API_TO_PAGE[path]}")

    # Also redirect /api/v1/incidents/{id} to incidents page
    if (
        request.method == "GET"
        and "text/html" in accept
        and path.startswith("/api/v1/incidents/")
        and "/trace" not in path
    ):
        return RedirectResponse(url="/#incidents")

    start = time.perf_counter()
    response: Response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    return response


# Error handling
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "path": request.url.path,
        },
    )


# Root route — serve the web dashboard
@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    """Serve the Sentinel web dashboard."""
    import pathlib

    template = pathlib.Path(__file__).parent / "templates" / "index.html"
    return HTMLResponse(content=template.read_text())


# Include routers
app.include_router(router)
app.include_router(metrics_router)
