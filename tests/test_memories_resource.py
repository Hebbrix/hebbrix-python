from unittest.mock import AsyncMock

import httpx
import pytest
from hebbrix import IndexingTimeoutError, MemoryClient
from hebbrix.resources import (
    CorrectionsResource,
    MemoriesResource,
    MemoryJobsResource,
    ProofLoopResource,
    SearchResource,
)


class RecordingClient:
    def __init__(self):
        self.calls = []

    async def post(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return {
            "results": [{"id": "memory-1"}],
            "processing_status": "completed",
            "searchable": True,
        }

    async def get(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return {"items": [], "has_more": False, "next_cursor": None}

    async def patch(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return {
            "id": "memory-1",
            "processing_status": "completed",
            "searchable": True,
        }

    async def delete(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return {}


@pytest.mark.asyncio
async def test_async_transport_copies_durable_recovery_headers_into_receipt():
    response = httpx.Response(
        202,
        json={
            "results": [{"id": "memory-1"}],
            "processing_status": "processing",
            "searchable": False,
        },
        headers={
            "X-Request-ID": "request-transport",
            "Location": "/v1/memories/memory-1",
            "X-Hebbrix-Index-Event": "event-transport",
            "X-Idempotent-Replay": "true",
            "Retry-After": "1",
        },
        request=httpx.Request("POST", "https://api.hebbrix.com/v1/memories"),
    )
    client = MemoryClient(api_key="test-key")
    client._client.request = AsyncMock(return_value=response)
    try:
        receipt = await client.post("/v1/memories", json={"content": "A fact"})
    finally:
        await client.close()

    assert receipt["request_id"] == "request-transport"
    assert receipt["status_url"] == "/v1/memories/memory-1"
    assert receipt["outbox_event_id"] == "event-transport"
    assert receipt["idempotency_replay"] is True
    assert receipt["retry_after"] == "1"


@pytest.mark.asyncio
async def test_create_forwards_every_supported_scope_and_source_field():
    client = RecordingClient()
    resource = MemoriesResource(client)

    await resource.create(
        content="A scoped fact",
        collection_id="collection-1",
        user_id="customer-7",
        agent_id="agent-2",
        run_id="run-3",
        app_id="support",
        namespace="production",
        importance=0.8,
        source_type="ticket",
        source_reference="ticket-42",
        metadata={"region": "us"},
        title="Customer ticket",
        tags=["support", "resolved"],
        source="zendesk",
        wait_for_index=True,
        async_dispatch=False,
    )

    path, request = client.calls[0]
    assert path == "/v1/memories"
    assert request["json"] == {
        "content": "A scoped fact",
        "collection_id": "collection-1",
        "user_id": "customer-7",
        "agent_id": "agent-2",
        "run_id": "run-3",
        "app_id": "support",
        "namespace": "production",
        "importance": 0.8,
        "source_type": "ticket",
        "source_reference": "ticket-42",
        "metadata": {"region": "us"},
        "infer": False,
        "wait_for_index": True,
        "async_dispatch": False,
        "title": "Customer ticket",
        "tags": ["support", "resolved"],
        "source": "zendesk",
    }


@pytest.mark.asyncio
async def test_create_allows_server_collection_resolution():
    client = RecordingClient()
    resource = MemoriesResource(client)

    await resource.create(content="A fact", user_id="customer-7")

    payload = client.calls[0][1]["json"]
    assert "collection_id" not in payload
    assert payload["user_id"] == "customer-7"


@pytest.mark.asyncio
async def test_create_sends_idempotency_as_transport_header_not_payload():
    client = RecordingClient()
    resource = MemoriesResource(client)

    await resource.create(content="A fact", idempotency_key="retry-7")

    request = client.calls[0][1]
    assert request["headers"] == {"Idempotency-Key": "retry-7"}
    assert "idempotency_key" not in request["json"]


@pytest.mark.asyncio
async def test_batch_create_has_one_truthful_readiness_contract():
    client = RecordingClient()

    async def post(path, **kwargs):
        client.calls.append((path, kwargs))
        return {
            "created": 1,
            "failed": 0,
            "memory_ids": ["memory-1"],
            "results": [{"id": "memory-1", "processing_status": "completed"}],
            "processing_status": "completed",
            "searchable": True,
        }

    client.post = post
    receipt = await MemoriesResource(client).create_batch(
        [{"content": "A batch fact"}],
        collection_id="collection-1",
        wait_for_index=True,
        idempotency_key="batch-retry-1",
    )

    path, request = client.calls[0]
    assert path == "/v1/memories/batch"
    assert receipt["searchable"] is True
    assert request["json"]["wait_for_index"] is True
    assert request["headers"] == {"Idempotency-Key": "batch-retry-1"}


@pytest.mark.asyncio
async def test_async_batch_polling_requires_every_item_to_be_searchable(monkeypatch):
    client = RecordingClient()
    calls = {"memory-1": 0, "memory-2": 0}

    async def get(path, **_kwargs):
        memory_id = path.rsplit("/", 1)[-1]
        calls[memory_id] += 1
        ready = calls[memory_id] >= 2
        return {
            "id": memory_id,
            "processing_status": "completed" if ready else "processing",
            "searchable": ready,
        }

    client.get = get
    monkeypatch.setattr("hebbrix.resources.asyncio.sleep", AsyncMock())
    receipt = await MemoriesResource(client).wait_batch_until_searchable(
        {
            "memory_ids": ["memory-1", "memory-2"],
            "processing_status": "processing",
            "searchable": False,
        },
        timeout=2,
        poll_interval=0.05,
    )

    assert receipt["processing_status"] == "completed"
    assert receipt["searchable"] is True
    assert {row["memory_id"] for row in receipt["results"]} == {
        "memory-1",
        "memory-2",
    }


@pytest.mark.asyncio
async def test_create_rejects_empty_content_before_network_io():
    client = RecordingClient()
    resource = MemoriesResource(client)

    with pytest.raises(ValueError, match="content or messages must be provided"):
        await resource.create(content="   ", user_id="customer-7")

    assert client.calls == []


@pytest.mark.asyncio
async def test_wait_for_index_polls_until_the_memory_is_actually_searchable(
    monkeypatch,
):
    client = RecordingClient()
    states = iter(
        [
            {"id": "memory-1", "processing_status": "processing", "searchable": False},
            {"id": "memory-1", "processing_status": "completed", "searchable": True},
        ]
    )

    async def post(_path, **_kwargs):
        return {
            "results": [{"id": "memory-1"}],
            "processing_status": "processing",
            "searchable": False,
        }

    async def get(_path, **_kwargs):
        return next(states)

    client.post = post
    client.get = get
    monkeypatch.setattr("hebbrix.resources.asyncio.sleep", AsyncMock())

    receipt = await MemoriesResource(client).create(
        content="A fact",
        wait_for_index=True,
        index_timeout=2,
        index_poll_interval=0.05,
    )

    assert receipt["searchable"] is True
    assert receipt["processing_status"] == "completed"


@pytest.mark.asyncio
async def test_single_create_timeout_preserves_the_original_durable_receipt():
    client = RecordingClient()
    durable_receipt = {
        "results": [{"id": "memory-1"}],
        "processing_status": "processing",
        "searchable": False,
        "outbox_event_id": "event-1",
        "status_url": "/v1/memories/memory-1",
        "request_id": "request-1",
        "idempotency_replay": False,
    }

    async def post(_path, **_kwargs):
        return dict(durable_receipt)

    async def get(_path, **_kwargs):
        return {
            "id": "memory-1",
            "processing_status": "processing",
            "searchable": False,
        }

    client.post = post
    client.get = get

    with pytest.raises(IndexingTimeoutError) as raised:
        await MemoriesResource(client).create(
            content="A durable fact",
            wait_for_index=True,
            idempotency_key="single-retry-1",
            index_timeout=0,
        )

    error = raised.value
    assert error.receipt == durable_receipt
    assert error.memory_ids == ["memory-1"]
    assert error.status_url == "/v1/memories/memory-1"
    assert error.request_id == "request-1"
    assert error.outbox_event_id == "event-1"
    assert error.idempotency_key == "single-retry-1"
    assert error.idempotency_replay is False
    assert isinstance(error.__cause__, TimeoutError)


@pytest.mark.asyncio
async def test_inference_job_timeout_preserves_the_job_receipt():
    client = RecordingClient()
    durable_receipt = {
        "job_id": "job-1",
        "processing_status": "processing",
        "status_url": "/v1/memory-jobs/job-1",
        "request_id": "request-2",
    }

    async def post(_path, **_kwargs):
        return dict(durable_receipt)

    async def get(_path, **_kwargs):
        return {"job_id": "job-1", "status": "processing"}

    client.post = post
    client.get = get

    with pytest.raises(IndexingTimeoutError) as raised:
        await MemoriesResource(client).create(
            messages=[{"role": "user", "content": "Remember this"}],
            infer=True,
            async_dispatch=True,
            wait_for_index=True,
            idempotency_key="inference-retry-1",
            index_timeout=0,
        )

    assert raised.value.receipt == durable_receipt
    assert raised.value.job_id == "job-1"
    assert raised.value.status_url == "/v1/memory-jobs/job-1"
    assert raised.value.idempotency_key == "inference-retry-1"
    assert isinstance(raised.value.__cause__, TimeoutError)


@pytest.mark.asyncio
async def test_batch_timeout_normalizes_recovery_metadata_from_durable_receipt():
    client = RecordingClient()
    durable_receipt = {
        "results": [{"id": "memory-1"}, {"memory_id": "memory-2"}],
        "memory_ids": ["memory-1", "memory-2"],
        "processing_status": "processing",
        "searchable": False,
        "outbox_event_id": "event-batch",
        "status_url": "/v1/memories/memory-1",
    }

    async def post(_path, **_kwargs):
        return dict(durable_receipt)

    async def get(path, **_kwargs):
        return {
            "id": path.rsplit("/", 1)[-1],
            "processing_status": "processing",
            "searchable": False,
        }

    client.post = post
    client.get = get

    with pytest.raises(IndexingTimeoutError) as raised:
        await MemoriesResource(client).create_batch(
            [{"content": "First"}, {"content": "Second"}],
            wait_for_index=True,
            idempotency_key="batch-retry-2",
            index_timeout=0,
        )

    assert raised.value.receipt == durable_receipt
    assert raised.value.memory_ids == ["memory-1", "memory-2"]
    assert raised.value.idempotency_key == "batch-retry-2"
    assert isinstance(raised.value.__cause__, TimeoutError)


@pytest.mark.asyncio
async def test_update_wait_timeout_preserves_receipt_without_repeating_patch():
    client = RecordingClient()
    durable_receipt = {
        "id": "memory-1",
        "processing_status": "processing",
        "searchable": False,
        "outbox_event_id": "event-update",
        "status_url": "/v1/memories/memory-1",
        "request_id": "request-update",
    }

    async def patch(path, **kwargs):
        client.calls.append((path, kwargs))
        return dict(durable_receipt)

    async def get(_path, **_kwargs):
        return {
            "id": "memory-1",
            "processing_status": "processing",
            "searchable": False,
        }

    client.patch = patch
    client.get = get

    with pytest.raises(IndexingTimeoutError) as raised:
        await MemoriesResource(client).update(
            "memory-1",
            content="Current truth",
            wait_for_index=True,
            index_timeout=0,
        )

    assert raised.value.receipt == durable_receipt
    assert raised.value.memory_ids == ["memory-1"]
    assert raised.value.outbox_event_id == "event-update"
    assert len(client.calls) == 1
    assert client.calls[0][0] == "/v1/memories/memory-1"


@pytest.mark.asyncio
async def test_wait_for_index_never_returns_a_failed_terminal_state():
    client = RecordingClient()

    async def post(_path, **_kwargs):
        return {
            "results": [{"id": "memory-1"}],
            "processing_status": "processing",
            "searchable": False,
        }

    async def get(_path, **_kwargs):
        return {"processing_status": "failed", "searchable": False}

    client.post = post
    client.get = get
    with pytest.raises(RuntimeError, match="terminal state failed"):
        await MemoriesResource(client).create(content="A fact", wait_for_index=True)


@pytest.mark.asyncio
async def test_wait_for_index_never_invents_searchability_from_completed_state():
    client = RecordingClient()

    async def get(_path, **_kwargs):
        return {"processing_status": "completed", "searchable": False}

    client.get = get
    with pytest.raises(RuntimeError, match="completed without searchable=true"):
        await MemoriesResource(client).wait_until_searchable("memory-1")


@pytest.mark.asyncio
async def test_create_supports_the_conversation_message_input_mode():
    client = RecordingClient()
    resource = MemoriesResource(client)
    messages = [
        {"role": "user", "content": "I prefer concise answers."},
        {"role": "assistant", "content": "Understood."},
    ]

    await resource.create(messages=messages, infer=True, user_id="customer-7")

    payload = client.calls[0][1]["json"]
    assert payload["messages"] == messages
    assert payload["infer"] is True
    assert "content" not in payload


@pytest.mark.asyncio
async def test_list_and_update_forward_scope_and_read_after_write_controls():
    client = RecordingClient()
    resource = MemoriesResource(client)

    await resource.list_page(
        collection_id="collection-1",
        user_id="user-1",
        agent_id="agent-1",
        run_id="run-1",
        include_superseded=True,
    )
    list_request = client.calls[-1][1]["params"]
    assert list_request["user_id"] == "user-1"
    assert list_request["agent_id"] == "agent-1"
    assert list_request["run_id"] == "run-1"
    assert list_request["include_superseded"] is True

    await resource.update("memory-1", content="Current truth", wait_for_index=True)
    update_request = client.calls[-1][1]["json"]
    assert update_request == {"content": "Current truth", "wait_for_index": True}


@pytest.mark.asyncio
async def test_memory_job_wait_polls_until_completed(monkeypatch):
    client = RecordingClient()
    resource = MemoryJobsResource(client)
    receipts = iter([{"status": "processing"}, {"status": "completed"}])

    async def get(_path, **_kwargs):
        return next(receipts)

    client.get = get
    monkeypatch.setattr("hebbrix.resources.asyncio.sleep", AsyncMock())

    receipt = await resource.wait("job-1", timeout=2, poll_interval=0.05)

    assert receipt["status"] == "completed"


@pytest.mark.asyncio
async def test_correction_and_proofloop_scopes_are_high_level_methods():
    client = RecordingClient()

    await CorrectionsResource(client).create(
        corrected_content="Use the safe rollout.",
        correction_type="procedural",
        collection_id="collection-1",
        user_id="tenant-1",
        agent_id="agent-1",
        idempotency_key="correction-1",
    )
    correction_path, correction_request = client.calls[-1]
    assert correction_path == "/v1/corrections"
    assert correction_request["headers"] == {"Idempotency-Key": "correction-1"}
    assert correction_request["json"]["user_id"] == "tenant-1"

    await ProofLoopResource(client).evaluate_policy(
        "rollout-policy",
        collection_id="collection-1",
        user_id="tenant-1",
        limit=250,
    )
    policy_path, policy_request = client.calls[-1]
    assert policy_path == "/v1/learning/policies/rollout-policy/evaluate"
    assert policy_request["json"]["limit"] == 250


class SearchRecordingClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def post(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return self.response


@pytest.mark.asyncio
async def test_search_with_proof_forwards_all_scope_and_quality_controls():
    response = {
        "results": [{"memory_id": "memory-1", "content": "fact", "score": 0.9}],
        "total": 1,
        "no_match": False,
        "abstain_recommended": False,
        "query_confidence": 0.9,
        "grounding": {"status": "supported"},
        "evidence_ids": ["memory-1"],
        "evidence_claims": [],
        "safety_contract_version": "search-safety-v1",
    }
    client = SearchRecordingClient(response)
    search = SearchResource(client)

    result = await search.search_with_proof(
        "question",
        collection_id="collection-1",
        user_id="user-1",
        agent_id="agent-1",
        run_id="run-1",
        fast=False,
        threshold=0.72,
        include_low_confidence=True,
        group_by_source=False,
        debug=True,
    )

    assert result["evidence_ids"] == ["memory-1"]
    payload = client.calls[0][1]["json"]
    assert payload["user_id"] == "user-1"
    assert payload["agent_id"] == "agent-1"
    assert payload["run_id"] == "run-1"
    assert payload["fast"] is False
    assert payload["threshold"] == 0.72
    assert payload["include_low_confidence"] is True
    assert payload["group_by_source"] is False
    assert payload["debug"] is True


@pytest.mark.asyncio
async def test_search_sdk_fails_closed_when_safety_metadata_is_missing():
    client = SearchRecordingClient(
        {"results": [{"memory_id": "nearest", "content": "wrong", "score": 1.0}]}
    )
    search = SearchResource(client)

    response = await search.search_with_proof("unknown attribute")

    assert response["results"] == []
    assert response["no_match"] is True
    assert response["abstain_recommended"] is True
    assert response["query_confidence"] == 0.0
    assert response["evidence_ids"] == []
    assert response["sdk_safety_reason"].startswith("missing_safety_fields:")


@pytest.mark.asyncio
async def test_search_sdk_preserves_evidence_bound_degraded_results():
    row = {"memory_id": "memory-1", "content": "exact fact", "score": 0.8}
    client = SearchRecordingClient(
        {
            "results": [row],
            "total": 1,
            "no_match": False,
            "abstain_recommended": True,
            "query_confidence": 0.45,
            "grounding": {"status": "degraded", "reason": "reranker_unavailable"},
            "evidence_ids": ["memory-1"],
            "evidence_claims": [],
            "safety_contract_version": "search-safety-v1",
            "degraded": True,
        }
    )

    response = await SearchResource(client).search_with_proof("exact fact")

    assert response["results"] == [row]
    assert response["no_match"] is False
    assert response["abstain_recommended"] is True
    assert response["sdk_safety_reason"] == "degraded_evidence_preserved"


@pytest.mark.asyncio
async def test_reason_forwards_scopes_facets_and_preserves_safety_envelope():
    response = {
        "answer": "Use Zed",
        "sources": [{"memory_id": "memory-1", "content": "Uses Zed", "score": 0.9}],
        "no_match": False,
        "abstain_recommended": False,
        "query_confidence": 0.9,
        "grounding": {"status": "supported"},
        "evidence_ids": ["memory-1"],
        "safety_contract_version": "search-safety-v1",
    }
    client = SearchRecordingClient(response)

    result = await SearchResource(client).reason(
        "Which editor?",
        collection_id="collection-1",
        user_id="user-1",
        agent_id="agent-1",
        run_id="run-1",
        facets=["editor"],
    )

    assert result["evidence_ids"] == ["memory-1"]
    payload = client.calls[0][1]["json"]
    assert payload["user_id"] == "user-1"
    assert payload["agent_id"] == "agent-1"
    assert payload["run_id"] == "run-1"
    assert payload["facets"] == ["editor"]
