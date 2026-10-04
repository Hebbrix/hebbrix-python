"""SDK contract controls, not model reliability or learning-performance tests."""

import copy
import json
from unittest.mock import AsyncMock, Mock

import pytest

from hebbrix.resources import ProofLoopResource
from hebbrix.sync_client import SyncProofLoopResource


def inputs():
    return dict(
        policy_key="integrity",
        candidates=[
            {"action_key": "a", "features": {"nested": ["original"]}},
            {"action_key": "b"},
        ],
        context={"scope": {"environment": "sandbox"}},
        collection_id="c",
        user_id="u",
        idempotency_key="once",
    )


def choice():
    return dict(
        chosen_action_key="b",
        action_probability=1.0,
        behavior_probabilities={"a": 0.0, "b": 1.0},
    )


async def invoke(kind, client, params, advisor):
    if kind == "sync":
        return SyncProofLoopResource(client).decide_with_advice(
            **params, advisor=advisor
        )

    async def callback(card):
        return advisor(card)

    return await ProofLoopResource(client).decide_with_advice(
        **params, advisor=callback
    )


def transport(kind):
    client = Mock()
    card = {"authorization_granted": False, "evidence_card": "untrusted"}
    client.get = (
        Mock(return_value=card) if kind == "sync" else AsyncMock(return_value=card)
    )
    client.post = (
        Mock(return_value={"decision_id": "d"})
        if kind == "sync"
        else AsyncMock(return_value={"decision_id": "d"})
    )
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("stage", ["evidence_read", "advisor"])
async def test_original_nested_inputs_survive_mutation(kind, stage):
    client, params, selected = transport(kind), inputs(), choice()
    original = copy.deepcopy(params)

    def mutate():
        params["context"]["scope"]["environment"] = "production"
        params["candidates"][0]["features"]["nested"].append("changed")
        params["candidates"].append({"action_key": "foreign"})

    if stage == "evidence_read":

        def read(*args, **kwargs):
            mutate()
            return {"authorization_granted": False}

        client.get.side_effect = read

    def callback(card):
        if stage == "advisor":
            mutate()
        return selected

    advisor = Mock(side_effect=callback)
    await invoke(kind, client, params, advisor)
    assert (
        json.loads(client.get.call_args.kwargs["params"]["context"])
        == original["context"]
    )
    body = client.post.call_args.kwargs["json"]
    assert body["context"] == original["context"]
    assert body["candidates"] == original["candidates"]
    assert body["user_id"] == "u" and body["collection_id"] == "c"
    assert body["mode"] == "observe" and body["idempotency_key"] == "once"
    advisor.assert_called_once()
    assert client.post.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["sync", "async"])
async def test_returned_distribution_is_not_a_mutable_transport_alias(kind):
    client, selected = transport(kind), choice()
    await invoke(kind, client, inputs(), Mock(return_value=selected))
    selected["behavior_probabilities"]["b"] = 0
    assert client.post.call_args.kwargs["json"]["behavior_probabilities"] == {
        "a": 0.0,
        "b": 1.0,
    }


BAD_CHOICES = [
    None,
    [],
    {**choice(), "user_id": "foreign"},
    {**choice(), "chosen_action_key": "foreign"},
    {**choice(), "chosen_action_key": None},
    {**choice(), "behavior_probabilities": None},
    {**choice(), "behavior_probabilities": {"b": 1}},
    {**choice(), "behavior_probabilities": {"a": 0, "b": 1, "c": 0}},
    {**choice(), "behavior_probabilities": {"a": 0, "b": True}},
    {**choice(), "behavior_probabilities": {"a": 0, "b": "1"}},
    {**choice(), "behavior_probabilities": {"a": 0, "b": float("nan")}},
    {**choice(), "behavior_probabilities": {"a": 0, "b": float("inf")}},
    {**choice(), "behavior_probabilities": {"a": -0.1, "b": 1.1}},
    {**choice(), "behavior_probabilities": {"a": 0.1, "b": 1}},
    {**choice(), "action_probability": True},
    {**choice(), "action_probability": "1"},
    {**choice(), "action_probability": None},
    {**choice(), "action_probability": float("nan")},
    {**choice(), "action_probability": 0},
    {**choice(), "action_probability": 1.1},
    {**choice(), "action_probability": 0.5},
    {
        "chosen_action_key": "b",
        "action_probability": 0,
        "behavior_probabilities": {"a": 1, "b": 0},
    },
]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("selected", BAD_CHOICES, ids=range(len(BAD_CHOICES)))
async def test_invalid_advisor_distribution_never_writes(kind, selected):
    client, advisor = transport(kind), Mock(return_value=selected)
    with pytest.raises(ValueError):
        await invoke(kind, client, inputs(), advisor)
    assert client.get.call_count == 1 and advisor.call_count == 1
    client.post.assert_not_called()


BAD_INPUTS = [
    {"policy_key": " invalid"},
    {"policy_key": "path/policy"},
    {"policy_key": {}},
    {"collection_id": {}},
    {"user_id": {}},
    {"idempotency_key": []},
    {"user_id": "x" * 256},
    {"idempotency_key": "x" * 161},
    {"candidates": []},
    {"candidates": [{"action_key": "a"}] * 2},
    {"candidates": [{"action_key": " a"}]},
    {"candidates": [{"action_key": True}]},
    {"candidates": [{"action_key": "a", "unexpected": "field"}]},
    {"candidates": [{"action_key": "a", "features": []}]},
    {"candidates": [{"action_key": "a", "description": 12}]},
    {"candidates": [{"action_key": str(i)} for i in range(51)]},
    {"context": []},
    {"context": {1: "not a JSON object key"}},
    {"context": {"x": float("nan")}},
    {"context": {"x": object()}},
    {"context": {"x": (1, 2)}},
    {"context": {"x": "x" * 17000}},
]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("bad", BAD_INPUTS, ids=range(len(BAD_INPUTS)))
async def test_invalid_inputs_fail_before_read_or_advisor(kind, bad):
    client, advisor = transport(kind), Mock(return_value=choice())
    with pytest.raises(ValueError):
        await invoke(kind, client, {**inputs(), **bad}, advisor)
    client.get.assert_not_called()
    advisor.assert_not_called()
    client.post.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "probabilities",
    [{"a": 0.3, "b": 0.7}, {"a": 0.0, "b": 1.0}, {"a": 0.3, "b": 0.700000005}],
)
async def test_valid_distribution_is_preserved_not_renormalized(kind, probabilities):
    client = transport(kind)
    selected = dict(
        chosen_action_key="b",
        action_probability=probabilities["b"],
        behavior_probabilities=probabilities,
    )
    await invoke(kind, client, inputs(), Mock(return_value=selected))
    assert (
        client.post.call_args.kwargs["json"]["behavior_probabilities"] == probabilities
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["sync", "async"])
async def test_single_action_requires_explicit_complete_distribution(kind):
    client = transport(kind)
    params = {**inputs(), "candidates": [{"action_key": "a"}]}
    await invoke(
        kind,
        client,
        params,
        Mock(
            return_value=dict(
                chosen_action_key="a",
                action_probability=1,
                behavior_probabilities={"a": 1},
            )
        ),
    )
    assert client.post.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("stage", ["read", "advisor", "write"])
async def test_failures_propagate_without_retry(kind, stage):
    client, advisor = transport(kind), Mock(return_value=choice())
    target = {"read": client.get, "advisor": advisor, "write": client.post}[stage]
    target.side_effect = RuntimeError("bounded failure")
    with pytest.raises(RuntimeError, match="bounded failure"):
        await invoke(kind, client, inputs(), advisor)
    assert client.get.call_count == 1
    assert advisor.call_count == (0 if stage == "read" else 1)
    assert client.post.call_count == (1 if stage == "write" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["sync", "async"])
async def test_cyclic_json_is_refused_before_read(kind):
    client, advisor, params = transport(kind), Mock(return_value=choice()), inputs()
    params["context"]["self"] = params["context"]
    with pytest.raises(ValueError):
        await invoke(kind, client, params, advisor)
    client.get.assert_not_called()
