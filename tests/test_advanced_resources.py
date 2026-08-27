"""Wire-contract regressions for every public advanced SDK family."""

import pytest
from hebbrix.resources import (
    CollectionsResource,
    ConsolidationResource,
    MemoryToolsResource,
    RLResource,
    TemporalResource,
    WorkingMemoryResource,
)


class RecordingClient:
    def __init__(self):
        self.calls = []

    async def get(self, path, **kwargs):
        self.calls.append(("GET", path, kwargs))
        if path == "/v1/collections":
            return {"items": [{"id": "collection-1"}], "has_more": False}
        return {"status": "success"}

    async def post(self, path, **kwargs):
        self.calls.append(("POST", path, kwargs))
        return {"status": "success"}

    async def delete(self, path, **kwargs):
        self.calls.append(("DELETE", path, kwargs))
        return {"status": "success"}


@pytest.mark.asyncio
async def test_advanced_resources_use_versioned_openapi_routes_and_shapes():
    client = RecordingClient()

    assert await CollectionsResource(client).list(limit=10) == [{"id": "collection-1"}]
    await RLResource(client).get_metrics()
    await TemporalResource(client).add_fact(
        subject="release",
        predicate="status",
        object="active",
        valid_from="2026-08-27T00:00:00Z",
    )
    working = WorkingMemoryResource(client)
    await working.add(role="user", content="hello", session_id="session-1")
    await working.get_context("session-1")
    await working.compress("session-1")
    await working.clear("session-1")
    await ConsolidationResource(client).get_stats("collection-1")
    await MemoryToolsResource(client).insert(
        collection_id="collection-1",
        content="durable fact",
        position=0,
        reason="contract test",
    )
    assert [(method, path) for method, path, _ in client.calls] == [
        ("GET", "/v1/collections"),
        ("GET", "/v1/rl/metrics"),
        ("POST", "/v1/temporal/facts"),
        ("POST", "/v1/working-memory/add"),
        ("GET", "/v1/working-memory/context/session-1"),
        ("POST", "/v1/working-memory/compress/session-1"),
        ("DELETE", "/v1/working-memory/clear/session-1"),
        ("GET", "/v1/consolidation/stats/collection-1"),
        ("POST", "/v1/memory-tools/insert"),
    ]

    temporal_body = client.calls[2][2]["json"]
    assert temporal_body["valid_from"] == "2026-08-27T00:00:00Z"
    assert temporal_body["subject_type"] == "ENTITY"
    assert temporal_body["object_type"] == "ENTITY"

    insert_body = client.calls[8][2]["json"]
    assert insert_body == {
        "collection_id": "collection-1",
        "content": "durable fact",
        "importance": 0.5,
        "metadata": {"requested_position": 0, "reason": "contract test"},
    }


@pytest.mark.asyncio
async def test_removed_advanced_operations_are_not_exported():
    client = RecordingClient()
    assert not hasattr(ConsolidationResource(client), "archive")
    from hebbrix import MemoryClient

    assert not hasattr(MemoryClient, "world_model")


@pytest.mark.asyncio
async def test_replace_requires_the_current_optimistic_concurrency_contract():
    resource = MemoryToolsResource(RecordingClient())
    with pytest.raises(ValueError, match="old_content and collection_id"):
        await resource.replace("memory-1", "new content")
