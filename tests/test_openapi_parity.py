"""Release guard: GA SDK methods must remain mapped to exported OpenAPI operations."""

import inspect

from hebbrix.resources import (
    CorrectionsResource,
    MemoriesResource,
    MemoryJobsResource,
    ProceduralResource,
    ProofLoopResource,
    SearchResource,
)
from hebbrix.sync_client import (
    SyncCorrectionsResource,
    SyncMemoriesResource,
    SyncMemoryJobsResource,
    SyncProceduralResource,
    SyncProofLoopResource,
    SyncSearchResource,
)

def test_async_and_sync_resources_cover_the_ga_lifecycle():
    required = {
        MemoriesResource: {
            "create",
            "create_batch",
            "wait_batch_until_searchable",
            "list_page",
            "get",
            "update",
            "delete",
        },
        MemoryJobsResource: {"get", "wait"},
        CorrectionsResource: {"create", "relevant", "get", "delete"},
        SearchResource: {"search_with_proof", "reason"},
        ProofLoopResource: {
            "decide",
            "get_decision",
            "define_metric",
            "list_metrics",
            "policy_insights",
            "evaluate_policy",
            "record_outcome",
            "proof",
            "public_key",
        },
        ProceduralResource: {"create", "list", "get", "update", "execute", "delete"},
        SyncMemoriesResource: {
            "create",
            "create_batch",
            "wait_batch_until_searchable",
            "list_page",
            "get",
            "update",
            "delete",
        },
        SyncMemoryJobsResource: {"get", "wait"},
        SyncCorrectionsResource: {"create", "relevant", "get", "delete"},
        SyncSearchResource: {"search_with_proof", "reason"},
        SyncProofLoopResource: {
            "decide",
            "get_decision",
            "define_metric",
            "list_metrics",
            "policy_insights",
            "evaluate_policy",
            "record_outcome",
            "proof",
            "public_key",
        },
        SyncProceduralResource: {
            "create",
            "list",
            "get",
            "update",
            "execute",
            "delete",
        },
    }
    missing = {
        resource.__name__: sorted(
            method
            for method in methods
            if not callable(getattr(resource, method, None))
        )
        for resource, methods in required.items()
    }
    assert {name: methods for name, methods in missing.items() if methods} == {}


def test_scoped_reason_and_read_after_write_are_typed_high_level_parameters():
    reason_params = inspect.signature(SearchResource.reason).parameters
    assert {"user_id", "agent_id", "run_id", "facets"} <= set(reason_params)

    update_params = inspect.signature(MemoriesResource.update).parameters
    assert "wait_for_index" in update_params

    create_params = inspect.signature(MemoriesResource.create).parameters
    assert {"user_id", "agent_id", "run_id", "idempotency_key"} <= set(create_params)
