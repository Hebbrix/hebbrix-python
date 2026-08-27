from hebbrix.sync_client import (
    SyncCorrectionsResource,
    SyncMemoriesResource,
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
        return {"id": "memory-1"}

    def delete(self, path, **kwargs):
        self.calls.append(("DELETE", path, kwargs))
        return {}


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
