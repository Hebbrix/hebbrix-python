"""Local wire/parity checks; no network, model, outcome study, or side effect."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from hebbrix.resources import ProofLoopResource, SearchResource
from hebbrix.sync_client import SyncProofLoopResource, SyncSearchResource
from hebbrix.chat import MemoryChat


def clients():
    sync, asynchronous = Mock(), Mock()
    for verb in ("get", "post"):
        getattr(sync, verb).return_value = {"authorization_granted": False}
        setattr(asynchronous, verb, AsyncMock(return_value={"authorization_granted": False}))
    return sync, asynchronous


@pytest.mark.asyncio
async def test_compact_advice_is_optional_and_preserves_scope():
    sync, asynchronous = clients()
    kwargs = dict(context={"issue": "delivery"}, user_id="owner-enduser", view="compact")
    assert SyncProofLoopResource(sync).policy_advice("policy:one", **kwargs) == await ProofLoopResource(asynchronous).policy_advice("policy:one", **kwargs)
    assert sync.get.call_args == asynchronous.get.call_args
    params = sync.get.call_args.kwargs["params"]
    assert params["view"] == "compact" and params["user_id"] == "owner-enduser"
    assert json.loads(params["context"]) == kwargs["context"]
    SyncProofLoopResource(sync).policy_advice("policy:one")
    assert "view" not in sync.get.call_args.kwargs["params"]


@pytest.mark.asyncio
async def test_compact_advisor_logs_only_external_choice_once():
    sync, asynchronous = clients()
    kwargs = dict(policy_key="p", context={"issue": "delivery"},
        candidates=[{"action_key": "a"}], view="compact")
    choice = {"chosen_action_key": "a", "action_probability": 1,
              "behavior_probabilities": {"a": 1}}
    SyncProofLoopResource(sync).decide_with_advice(advisor=Mock(return_value=choice), **kwargs)
    await ProofLoopResource(asynchronous).decide_with_advice(advisor=AsyncMock(return_value=choice), **kwargs)
    assert sync.get.call_args == asynchronous.get.call_args
    assert sync.post.call_args == asynchronous.post.call_args
    assert sync.get.call_args.kwargs["params"]["view"] == "compact"
    assert sync.post.call_args.kwargs["json"]["mode"] == "observe"
    assert "view" not in sync.post.call_args.kwargs["json"]


@pytest.mark.asyncio
async def test_batch_parity_detaches_requests_and_does_not_retry_rejections():
    sync, asynchronous = clients()
    items = [{"policy_key": "p", "context": {"issue": "delivery"},
              "candidates": [{"action_key": "explain"}], "idempotency_key": "d1",
              "proof_context": {"token": "original-token"}}]
    sync_result = SyncProofLoopResource(sync).decide_batch(items)
    async_result = await ProofLoopResource(asynchronous).decide_batch(items)
    assert sync_result == async_result
    assert sync.post.call_args == asynchronous.post.call_args
    assert sync.post.call_args.args == ("/v1/learning/decisions/batch",)
    assert sync.post.call_args.kwargs["json"]["items"][0]["proof_context_token"] == "original-token"
    assert items[0]["proof_context"] == {"token": "original-token"}
    items[0]["context"]["issue"] = "foreign"
    assert sync.post.call_args.kwargs["json"]["items"][0]["context"]["issue"] == "delivery"
    assert sync.post.call_count == asynchronous.post.call_count == 1
    outcomes = [{"decision_id": "d", "idempotency_key": "o1", "outcome": {"success": False}}]
    SyncProofLoopResource(sync).record_outcomes_batch(outcomes, view="full")
    await ProofLoopResource(asynchronous).record_outcomes_batch(outcomes, view="full")
    assert sync.post.call_args == asynchronous.post.call_args
    assert sync.post.call_args.args == ("/v1/learning/outcomes/batch",)


@pytest.mark.parametrize("items", [[], [{}] * 51, [{}], [{"idempotency_key": " "}],
    [{"idempotency_key": "k", "value": float("nan")}], ["not-an-object"],
    [{"idempotency_key": "k", "proof_context": {}}],
    [{"idempotency_key": "k", "proof_context": "a", "proof_context_token": "b"}]])
def test_batch_invalid_inputs_fail_before_network(items):
    client = Mock()
    with pytest.raises(ValueError):
        SyncProofLoopResource(client).decide_batch(items)
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_confirmation_requires_affirmation_and_exact_scope():
    sync, asynchronous = clients()
    fields = dict(observation_id="captured-1", idempotency_key="confirmed-1",
        success=False, confirmed=True, collection_id="c", user_id="enduser",
        source_system="owner-confirmation", source_event_id="event-1")
    SyncProofLoopResource(sync).confirm_capture("decision/one", **fields)
    await ProofLoopResource(asynchronous).confirm_capture("decision/one", **fields)
    assert sync.post.call_args == asynchronous.post.call_args
    assert sync.post.call_args.args == ("/v1/learning/decisions/decision%2Fone/confirm-capture",)
    assert sync.post.call_args.kwargs["json"] == fields


@pytest.mark.parametrize("patch", [{"success": 1}, {"success": "false"},
    {"confirmed": False}, {"confirmed": 1}, {"observation_id": ""},
    {"idempotency_key": " "}])
def test_confirmation_never_infers_or_implicitly_finalizes(patch):
    client = Mock()
    fields = dict(observation_id="o", idempotency_key="i", success=False, confirmed=True)
    fields.update(patch)
    with pytest.raises(ValueError):
        SyncProofLoopResource(client).confirm_capture("d", **fields)
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_compact_search_retains_bound_safety_receipt():
    receipt = {"query": "delivery", "results": [{"memory_id": "m", "content": "Delayed",
        "score": 0.9, "raw_rerank_score": 12.321, "metadata": {"known_failure": True}}],
        "total": 1, "no_match": False, "abstain_recommended": False,
        "query_confidence": 0.9, "grounding": {"status": "supported"},
        "evidence_ids": ["m"], "safety_contract_version": "search-safety-v1"}
    sync, asynchronous = clients()
    sync.post.return_value = receipt
    asynchronous.post.return_value = receipt
    first = SyncSearchResource(sync).search_with_proof("delivery", view="compact", user_id="u")
    second = await SearchResource(asynchronous).search_with_proof("delivery", view="compact", user_id="u")
    assert first == second
    assert first["results"][0]["raw_rerank_score"] == 12.321
    assert first["evidence_ids"] == ["m"]
    assert sync.post.call_args == asynchronous.post.call_args
    assert sync.post.call_args.kwargs["json"]["view"] == "compact"


@pytest.mark.parametrize("view", ["unknown", True, 1])
def test_invalid_view_fails_before_read(view):
    client = Mock()
    with pytest.raises(ValueError):
        SyncProofLoopResource(client).policy_advice("p", view=view)
    client.get.assert_not_called()


def test_chat_readiness_returns_original_job_receipt_without_duplicate_write():
    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": "Noted"}}],
        "memory_context": {"memory_learning": {"job_id": "j", "poll_url": "/v1/memory-jobs/j",
            "wait_status": "deadline_reached"}}, "usage": {}, "model": "test"}
    chat = MemoryChat(api_key="local-test", model="test")
    with patch("hebbrix.chat.requests.post", return_value=response) as post:
        result = chat.send_with_context("A fact", "u", wait_for_learning_seconds=2)
    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["wait_for_learning_seconds"] == 2
    assert result["memory_context"]["memory_learning"]["job_id"] == "j"


@pytest.mark.parametrize("wait", [-1, 21, float("nan"), True])
def test_chat_readiness_bound_fails_before_request(wait):
    chat = MemoryChat(api_key="local-test", model="test")
    with patch("hebbrix.chat.requests.post") as post:
        with pytest.raises(ValueError):
            chat.send("A fact", "u", wait_for_learning_seconds=wait)
    post.assert_not_called()


def test_package_docs_metadata_uses_canonical_host():
    root = Path(__file__).parents[1]
    text = (root / "pyproject.toml").read_text()
    assert 'Documentation = "https://hebbrix.com/docs"' in text
    assert "docs.hebbrix.com" not in text
    readme = (root / "README.md").read_text()
    assert "pip install hebbrix==2.6.2" in readme
    assert "three calls" in readme
    assert "schema `" not in readme
