"""Compact is the SDK search default (customer report 2026-10-18, issue 12)."""

from unittest.mock import AsyncMock, Mock

import pytest
from hebbrix.resources import SearchResource
from hebbrix.sync_client import SyncSearchResource

ENVELOPE = {
    "query": "q",
    "results": [{"memory_id": "m", "content": "fact", "score": 0.9}],
    "total": 1,
    "no_match": False,
    "abstain_recommended": False,
    "query_confidence": 0.9,
    "grounding": {"status": "supported"},
    "evidence_ids": ["m"],
    "safety_contract_version": "search-safety-v1",
    "view": "compact",
    "query_entities": [],
    "profile": {"status": "ok", "facts": [], "count": 0},
}


def clients():
    sync, asynchronous = Mock(), Mock()
    sync.post.return_value = dict(ENVELOPE)
    asynchronous.post = AsyncMock(return_value=dict(ENVELOPE))
    return sync, asynchronous


@pytest.mark.asyncio
async def test_search_with_proof_defaults_to_compact_and_keeps_proof():
    sync, asynchronous = clients()
    first = SyncSearchResource(sync).search_with_proof("q", user_id="u")
    second = await SearchResource(asynchronous).search_with_proof("q", user_id="u")
    assert first == second
    assert sync.post.call_args == asynchronous.post.call_args
    body = sync.post.call_args.kwargs["json"]
    assert body["view"] == "compact"
    # The proof token stays the server default for proof-bound workflows.
    assert "include_proof_context" not in body
    # Opt-in fields are absent unless enabled (older servers reject unknowns).
    assert "prefer_entity_match" not in body and "include_profile" not in body
    assert first["view"] == "compact" and first["profile"]["status"] == "ok"


@pytest.mark.asyncio
async def test_rows_only_search_does_not_request_the_proof_token():
    sync, asynchronous = clients()
    rows = SyncSearchResource(sync).search("q", user_id="u")
    assert rows == ENVELOPE["results"]
    await SearchResource(asynchronous).search("q", user_id="u")
    for client in (sync, asynchronous):
        body = client.post.call_args.kwargs["json"]
        assert body["view"] == "compact"
        assert body["include_proof_context"] is False


@pytest.mark.asyncio
async def test_full_view_debug_and_new_options_are_explicit():
    sync, asynchronous = clients()
    kwargs = dict(
        user_id="u",
        view="full",
        debug=True,
        prefer_entity_match=True,
        include_profile=True,
        include_proof_context=True,
    )
    SyncSearchResource(sync).search_with_proof("q", **kwargs)
    await SearchResource(asynchronous).search_with_proof("q", **kwargs)
    assert sync.post.call_args == asynchronous.post.call_args
    body = sync.post.call_args.kwargs["json"]
    assert body["view"] == "full" and body["debug"] is True
    assert body["prefer_entity_match"] is True and body["include_profile"] is True
    assert body["include_proof_context"] is True
    SyncSearchResource(sync).search("q", user_id="u", include_proof_context=True)
    assert sync.post.call_args.kwargs["json"]["include_proof_context"] is True


def test_invalid_view_still_fails_before_the_request():
    sync, _ = clients()
    with pytest.raises(ValueError, match="view must be full or compact"):
        SyncSearchResource(sync).search_with_proof("q", view="tiny")
    sync.post.assert_not_called()


REASON = {
    "answer": "a",
    "sources": [{"memory_id": "m", "content": "fact", "score": 0.9}],
    "metadata": {},
    "no_match": False,
    "abstain_recommended": False,
    "query_confidence": 0.9,
    "grounding": {"status": "supported"},
    "evidence_ids": ["m"],
    "safety_contract_version": "search-safety-v1",
}


@pytest.mark.asyncio
async def test_reason_defaults_to_compact_and_debug_is_explicit():
    sync, asynchronous = Mock(), Mock()
    sync.post.return_value = dict(REASON)
    asynchronous.post = AsyncMock(return_value=dict(REASON))
    SyncSearchResource(sync).reason("q", user_id="u")
    await SearchResource(asynchronous).reason("q", user_id="u")
    assert sync.post.call_args == asynchronous.post.call_args
    body = sync.post.call_args.kwargs["json"]
    assert body["view"] == "compact"
    assert "debug" not in body
    SyncSearchResource(sync).reason("q", user_id="u", view="full", debug=True)
    body = sync.post.call_args.kwargs["json"]
    assert body["view"] == "full" and body["debug"] is True
    with pytest.raises(ValueError):
        SyncSearchResource(sync).reason("q", user_id="u", view="tiny")
