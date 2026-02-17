"""Shared application state and dependency injection for the API."""

from __future__ import annotations

from typing import Any

from agent.core import IncidentAnalyzer
from agent.models import IncidentReport
from rag.engine import RAGEngine


class IncidentStore:
    """Dict-like incident store backed by DynamoDB (production) or in-memory (local/test).

    When *table_name* is provided, all reads and writes go to DynamoDB.
    When *table_name* is ``None``, a plain in-memory dict is used instead.
    """

    def __init__(self, table_name: str | None = None) -> None:
        self._table_name = table_name
        self._memory: dict[str, IncidentReport] = {}
        self._table = None

    def _dynamo_table(self) -> Any:
        if self._table is None:
            import boto3

            self._table = boto3.resource("dynamodb").Table(self._table_name)
        return self._table

    @property
    def _use_dynamo(self) -> bool:
        return self._table_name is not None

    def __setitem__(self, key: str, value: IncidentReport) -> None:
        if self._use_dynamo:
            self._dynamo_table().put_item(
                Item={
                    "incident_id": key,
                    "data": value.model_dump_json(),
                },
            )
        else:
            self._memory[key] = value

    def __getitem__(self, key: str) -> IncidentReport:
        if self._use_dynamo:
            resp = self._dynamo_table().get_item(Key={"incident_id": key})
            item = resp.get("Item")
            if item is None:
                raise KeyError(key)
            return IncidentReport.model_validate_json(item["data"])
        return self._memory[key]

    def __contains__(self, key: object) -> bool:
        if self._use_dynamo:
            resp = self._dynamo_table().get_item(
                Key={"incident_id": key},
                ProjectionExpression="incident_id",
            )
            return "Item" in resp
        return key in self._memory

    def values(self) -> list[IncidentReport]:
        """Return all stored incidents."""
        if self._use_dynamo:
            return self._scan_all()
        return list(self._memory.values())

    def __len__(self) -> int:
        if self._use_dynamo:
            return len(self._scan_all())
        return len(self._memory)

    def __bool__(self) -> bool:
        if self._use_dynamo:
            resp = self._dynamo_table().scan(Limit=1, Select="COUNT")
            return bool(resp["Count"] > 0)
        return bool(self._memory)

    def clear(self) -> None:
        self._memory.clear()

    def _scan_all(self) -> list[IncidentReport]:
        items: list[IncidentReport] = []
        table = self._dynamo_table()
        resp = table.scan()
        for item in resp.get("Items", []):
            items.append(IncidentReport.model_validate_json(item["data"]))
        while resp.get("LastEvaluatedKey"):
            resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            for item in resp.get("Items", []):
                items.append(IncidentReport.model_validate_json(item["data"]))
        return items


_analyzer: IncidentAnalyzer | None = None
_rag_engine: RAGEngine | None = None
_incident_store: IncidentStore = IncidentStore()


def init_analyzer(analyzer: IncidentAnalyzer) -> None:
    global _analyzer
    _analyzer = analyzer


def init_rag_engine(engine: RAGEngine) -> None:
    global _rag_engine
    _rag_engine = engine


def init_incident_store(store: IncidentStore) -> None:
    global _incident_store
    _incident_store = store


def get_analyzer() -> IncidentAnalyzer:
    assert _analyzer is not None, "IncidentAnalyzer not initialized"
    return _analyzer


def get_rag_engine() -> RAGEngine | None:
    return _rag_engine


def get_incident_store() -> IncidentStore:
    return _incident_store
