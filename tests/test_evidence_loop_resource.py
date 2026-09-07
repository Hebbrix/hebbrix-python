"""Sync/async wire parity for the protected evidence lifecycle."""

import inspect
from unittest.mock import AsyncMock, Mock

import pytest

from hebbrix.resources import ProofLoopResource
from hebbrix.sync_client import SyncProofLoopResource


SCOPE = {
    "policy_key": "workflow.choice",
    "collection_id": "collection",
    "user_id": "end-user",
}
DELIVERY = {
    "decision_id": "decision",
    "source_event_id": "source-event",
    "evidence_digest": "a" * 64,
    "execution_digest": "b" * 64,
    "observations": [
        {
            "metric_key": "success",
            "value": 1,
            "is_final": False,
            "observed_at": "2026-09-07T12:00:00Z",
        }
    ],
}
CLAIM = {
    "attempt_id": "attempt",
    "status": "started",
    "actual_action_key": "baseline",
    "arguments_digest": "c" * 64,
}

CASES = [
    (
        "register_verifier",
        (),
        {
            **SCOPE,
            "api_key_id": "key",
            "source_system": "verifier",
            "metric_keys": ["success"],
        },
        "post",
        "/v1/learning/verifiers",
    ),
    (
        "create_episode",
        (),
        {**SCOPE, "verifier_id": "verifier", "idempotency_key": "episode-key"},
        "post",
        "/v1/learning/episodes",
    ),
    (
        "revoke_verifier",
        ("verifier",),
        {},
        "post",
        "/v1/learning/verifiers/verifier/revoke",
    ),
    (
        "get_episode",
        ("episode",),
        {"offset": 100},
        "get",
        "/v1/learning/episodes/episode",
    ),
    (
        "close_episode",
        ("episode",),
        {"status": "interrupted"},
        "post",
        "/v1/learning/episodes/episode/close",
    ),
    (
        "record_execution",
        ("decision",),
        CLAIM,
        "post",
        "/v1/learning/decisions/decision/executions",
    ),
    (
        "assessment",
        ("decision",),
        {"evidence_offset": 100},
        "get",
        "/v1/learning/decisions/decision/assessment",
    ),
    (
        "verifier_evidence",
        ("verifier", "decision"),
        {},
        "get",
        "/v1/learning/verifiers/verifier/decisions/decision",
    ),
    (
        "deliver_verified_outcomes",
        ("verifier",),
        DELIVERY,
        "post",
        "/v1/learning/verifiers/verifier/events",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("resource_class", [ProofLoopResource, SyncProofLoopResource])
@pytest.mark.parametrize("name,args,kwargs,method,path", CASES)
async def test_protected_wire_contract_preserves_server_receipt(
    resource_class, name, args, kwargs, method, path
):
    receipt = {
        "authorization_granted": False,
        "status": "review_required",
        "replayed": True,
    }
    transport = Mock()
    call = (
        AsyncMock(return_value=receipt)
        if resource_class is ProofLoopResource
        else Mock(return_value=receipt)
    )
    setattr(transport, method, call)
    result = getattr(resource_class(transport), name)(*args, **kwargs)
    if inspect.isawaitable(result):
        result = await result
    assert result is receipt
    expected = (
        {"json" if method == "post" else "params": kwargs}
        if kwargs or method == "post"
        else {}
    )
    call.assert_called_once_with(path, **expected)


@pytest.mark.parametrize("resource_class", [ProofLoopResource, SyncProofLoopResource])
@pytest.mark.asyncio
async def test_source_delivery_does_not_fall_back_to_unprotected_endpoint(
    resource_class,
):
    transport = Mock()
    error = RuntimeError("verifier credential rejected")
    transport.post = (
        AsyncMock(side_effect=error)
        if resource_class is ProofLoopResource
        else Mock(side_effect=error)
    )
    with pytest.raises(RuntimeError, match="verifier credential rejected"):
        result = resource_class(transport).deliver_verified_outcomes(
            "verifier", **DELIVERY
        )
        if inspect.isawaitable(result):
            await result
    assert transport.post.call_count == 1
