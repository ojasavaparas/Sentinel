"""FastAPI application — main entrypoint for the Sentinel API."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from agent.core import IncidentAnalyzer
from agent.llm_client import create_client
from api.deps import init_analyzer, init_rag_engine
from api.routes import metrics_router, router
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


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next: Any) -> Response:
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


# Root route
@app.get("/")
async def root() -> dict[str, Any]:
    """Landing page with API overview."""
    return {
        "name": "Sentinel",
        "description": "Multi-agent AI system for automated production incident analysis",
        "version": "0.1.0",
        "endpoints": {
            "analyze": "POST /api/v1/analyze",
            "analyze_stream": "POST /api/v1/analyze/stream",
            "incidents": "GET /api/v1/incidents",
            "health": "GET /api/v1/health",
            "docs": "GET /docs",
        },
    }


# Include routers
app.include_router(router)
app.include_router(metrics_router)
