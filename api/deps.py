"""Shared application state and dependency injection for the API."""

from __future__ import annotations

from agent.core import IncidentAnalyzer
from agent.models import IncidentReport
from rag.engine import RAGEngine

# In-memory stores (initialized at startup)
_analyzer: IncidentAnalyzer | None = None
_rag_engine: RAGEngine | None = None
_incident_store: dict[str, IncidentReport] = {}


def init_analyzer(analyzer: IncidentAnalyzer) -> None:
    global _analyzer
    _analyzer = analyzer


def init_rag_engine(engine: RAGEngine) -> None:
    global _rag_engine
    _rag_engine = engine


def get_analyzer() -> IncidentAnalyzer:
    assert _analyzer is not None, "IncidentAnalyzer not initialized"
    return _analyzer


def get_rag_engine() -> RAGEngine | None:
    return _rag_engine


def get_incident_store() -> dict[str, IncidentReport]:
    return _incident_store
