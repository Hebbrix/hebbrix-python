import httpx
import pytest
from hebbrix import IndexingTimeoutError
from hebbrix.sync_client import (
    SyncCorrectionsResource,
    SyncMemoriesResource,
    SyncMemoryClient,
    SyncProofLoopResource,
    SyncSearchResource,
)


class RecordingSyncClient:
    def __init__(self):
        self.calls = []

    def post(self, path, **kwargs):
        self.calls.append(("POST", path, kwargs))
        return {
            "decision_id": "decision-1",
            "processing_status": "completed",
            "searchable": True,
        }

    def get(self, path, **kwargs):
        self.calls.append(("GET", path, kwargs))
        return {"key_id": "key-1"}

    def patch(self, path, **kwargs):
        self.calls.append(("PATCH", path, kwargs))
        return {
            "id": "memory-1",
            "processing_status": "completed",
            "searchable": True,
        }

    def delete(self, path, **kwargs):
        self.calls.append(("DELETE", path, kwargs))
        return {}


def test_sync_transport_copies_durable_recovery_headers_into_receipt():
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
    client = SyncMemoryClient(api_key="test-key")
    client._client.request = lambda *_args, **_kwargs: response
    try:
        receipt = client.post("/v1/memories", json={"content": "A fact"})
    finally:
        client.close()

    assert receipt["request_id"] == "request-transport"
    assert receipt["status_url"] == "/v1/memories/memory-1"
    assert receipt["outbox_event_id"] == "event-transport"
    assert receipt["idempotency_replay"] is True
    assert receipt["retry_after"] == "1"


def test_sync_create_matches_all_async_memory_create_fields():
    client = RecordingSyncClient()
    memories = SyncMemoriesResource(client)

    memories.create(
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

    assert client.calls[0][1] == "/v1/memories"
    assert client.calls[0][2]["json"]["user_id"] == "customer-7"
    assert client.calls[0][2]["json"]["wait_for_index"] is True
    assert client.calls[0][2]["json"]["tags"] == ["support", "resolved"]


def test_sync_memory_and_correction_lifecycle_expose_scope_and_idempotency():
    client = RecordingSyncClient()
    memories = SyncMemoriesResource(client)

    memories.list_page(
        collection_id="collection-1",
        user_id="user-1",
        agent_id="agent-1",
        run_id="run-1",
    )
    assert client.calls[-1][2]["params"]["user_id"] == "user-1"

    memories.update("memory-1", content="Current truth", wait_for_index=True)
    assert client.calls[-1][2]["json"]["wait_for_index"] is True

    SyncCorrectionsResource(client).create(
        corrected_content="Use the current truth",
        collection_id="collection-1",
        user_id="user-1",
        idempotency_key="correction-1",
    )
    assert client.calls[-1][2]["headers"] == {"Idempotency-Key": "correction-1"}


def test_sync_single_create_timeout_preserves_original_receipt_and_cause():
    class PendingClient(RecordingSyncClient):
        def post(self, path, **kwargs):
            self.calls.append(("POST", path, kwargs))
            return {
                "results": [{"id": "memory-1"}],
                "processing_status": "processing",
                "searchable": False,
                "outbox_event_id": "event-1",
                "status_url": "/v1/memories/memory-1",
                "request_id": "request-1",
            }

        def get(self, path, **kwargs):
            self.calls.append(("GET", path, kwargs))
            return {
                "id": "memory-1",
                "processing_status": "processing",
                "searchable": False,
            }

    client = PendingClient()
    with pytest.raises(IndexingTimeoutError) as raised:
        SyncMemoriesResource(client).create(
            content="A durable fact",
            wait_for_index=True,
            idempotency_key="sync-retry-1",
            index_timeout=0,
        )

    assert raised.value.memory_ids == ["memory-1"]
    assert raised.value.request_id == "request-1"
    assert raised.value.outbox_event_id == "event-1"
    assert raised.value.idempotency_key == "sync-retry-1"
    assert isinstance(raised.value.__cause__, TimeoutError)
    assert sum(call[0] == "POST" for call in client.calls) == 1


def test_sync_inference_job_timeout_preserves_job_recovery_metadata():
    class PendingJobClient(RecordingSyncClient):
        def post(self, path, **kwargs):
            self.calls.append(("POST", path, kwargs))
            return {
                "job_id": "job-1",
                "processing_status": "processing",
                "status_url": "/v1/memory-jobs/job-1",
            }

        def get(self, path, **kwargs):
            self.calls.append(("GET", path, kwargs))
            return {"job_id": "job-1", "status": "processing"}

    with pytest.raises(IndexingTimeoutError) as raised:
        SyncMemoriesResource(PendingJobClient()).create(
            messages=[{"role": "user", "content": "Remember this"}],
            infer=True,
            async_dispatch=True,
            wait_for_index=True,
            idempotency_key="sync-job-retry-1",
            index_timeout=0,
        )

    assert raised.value.job_id == "job-1"
    assert raised.value.status_url == "/v1/memory-jobs/job-1"
    assert raised.value.idempotency_key == "sync-job-retry-1"
    assert isinstance(raised.value.__cause__, TimeoutError)


def test_sync_update_wait_timeout_preserves_receipt_and_only_patches_once():
    class PendingUpdateClient(RecordingSyncClient):
        def patch(self, path, **kwargs):
            self.calls.append(("PATCH", path, kwargs))
            return {
                "id": "memory-1",
                "processing_status": "processing",
                "searchable": False,
                "outbox_event_id": "event-update",
                "status_url": "/v1/memories/memory-1",
            }

        def get(self, path, **kwargs):
            self.calls.append(("GET", path, kwargs))
            return {
                "id": "memory-1",
                "processing_status": "processing",
                "searchable": False,
            }

    client = PendingUpdateClient()
    with pytest.raises(IndexingTimeoutError) as raised:
        SyncMemoriesResource(client).update(
            "memory-1",
            content="Current truth",
            wait_for_index=True,
            index_timeout=0,
        )

    assert raised.value.memory_ids == ["memory-1"]
    assert raised.value.outbox_event_id == "event-update"
    assert sum(call[0] == "PATCH" for call in client.calls) == 1


def test_sync_batch_timeout_preserves_receipt_and_idempotency_metadata():
    class PendingBatchClient(RecordingSyncClient):
        def post(self, path, **kwargs):
            self.calls.append(("POST", path, kwargs))
            return {
                "memory_ids": ["memory-1", "memory-2"],
                "processing_status": "processing",
                "searchable": False,
                "outbox_event_id": "event-batch",
                "status_url": "/v1/memories/memory-1",
            }

        def get(self, path, **kwargs):
            self.calls.append(("GET", path, kwargs))
            return {
                "id": path.rsplit("/", 1)[-1],
                "processing_status": "processing",
                "searchable": False,
            }

    with pytest.raises(IndexingTimeoutError) as raised:
        SyncMemoriesResource(PendingBatchClient()).create_batch(
            [{"content": "First"}, {"content": "Second"}],
            wait_for_index=True,
            idempotency_key="sync-batch-retry-1",
            index_timeout=0,
        )

    assert raised.value.memory_ids == ["memory-1", "memory-2"]
    assert raised.value.outbox_event_id == "event-batch"
    assert raised.value.idempotency_key == "sync-batch-retry-1"
    assert isinstance(raised.value.__cause__, TimeoutError)


def test_sync_proofloop_supports_rotated_public_key_lookup():
    client = RecordingSyncClient()
    proofloop = SyncProofLoopResource(client)

    proofloop.public_key("a" * 64)

    assert client.calls == [
        ("GET", "/v1/learning/proof-key", {"params": {"key_id": "a" * 64}})
    ]


def test_sync_reason_forwards_scopes_and_preserves_safety_envelope():
    class ReasonClient(RecordingSyncClient):
        def post(self, path, **kwargs):
            self.calls.append(("POST", path, kwargs))
            return {
                "answer": "Use Zed",
                "sources": [
                    {"memory_id": "memory-1", "content": "Uses Zed", "score": 0.9}
                ],
                "no_match": False,
                "abstain_recommended": False,
                "query_confidence": 0.9,
                "grounding": {"status": "supported"},
                "evidence_ids": ["memory-1"],
                "safety_contract_version": "search-safety-v1",
            }

    client = ReasonClient()
    result = SyncSearchResource(client).reason(
        "Which editor?",
        collection_id="collection-1",
        user_id="user-1",
        agent_id="agent-1",
        run_id="run-1",
        facets=["editor"],
    )

    assert result["evidence_ids"] == ["memory-1"]
    payload = client.calls[0][2]["json"]
    assert payload["user_id"] == "user-1"
    assert payload["agent_id"] == "agent-1"
    assert payload["run_id"] == "run-1"
    assert payload["facets"] == ["editor"]
