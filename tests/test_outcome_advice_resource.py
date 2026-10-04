"""New policy/advice wire contracts, no network or credentials."""
import json
from unittest.mock import AsyncMock, Mock
import pytest
from hebbrix.resources import ProofLoopResource
from hebbrix.sync_client import SyncProofLoopResource


@pytest.mark.asyncio
@pytest.mark.parametrize("method,args,kwargs,verb,path", [
    ("register_context_schema", ("a/b",), {"context_schema": {"fields": {}}}, "request", "/v1/learning/policies/a%2Fb/context-schema"),
    ("context_schema", ("a/b",), {}, "get", "/v1/learning/policies/a%2Fb/context-schema"),
    ("configure_policy", ("a/b",), {"configuration": {"actions": {}}}, "request", "/v1/learning/policies/a%2Fb/configuration"),
    ("policy_configuration", ("a/b",), {}, "get", "/v1/learning/policies/a%2Fb/configuration"),
    ("policy_advice", ("a/b",), {"context": {"x": "a b"}}, "get", "/v1/learning/policies/a%2Fb/advice"),
    ("policy_advice", ("a/b",), {"context": {}, "remaining_decisions": 100, "max_pilot_decisions": 2}, "get", "/v1/learning/policies/a%2Fb/advice"),
    ("action_advice", ("Restart sandbox",), {"policy_key": "p", "action_key": "a", "user_id": "scoped"}, "get", "/v1/confidence"),
])
async def test_sync_async_policy_wire_parity(method, args, kwargs, verb, path):
    sync, asynchronous = Mock(), Mock()
    setattr(asynchronous, verb, AsyncMock(return_value={"authorization_granted": False}))
    getattr(sync, verb).return_value = {"authorization_granted": False}
    first = getattr(SyncProofLoopResource(sync), method)(*args, **kwargs)
    second = await getattr(ProofLoopResource(asynchronous), method)(*args, **kwargs)
    assert first == second
    call = getattr(sync, verb).call_args
    assert call == getattr(asynchronous, verb).call_args
    assert path in call.args
    if method == "configure_policy":
        assert call.args[0] == "PUT" and call.kwargs["json"]["expected_revision"] == 0
    if method == "policy_advice":
        assert json.loads(call.kwargs["params"]["context"]) == kwargs["context"]
        for key in ("remaining_decisions", "max_pilot_decisions"):
            if key in kwargs:
                assert call.kwargs["params"][key] == kwargs[key]
    if method == "action_advice":
        assert call.kwargs["params"]["end_user_id"] == "scoped"
        assert "user_id" not in call.kwargs["params"]


@pytest.mark.asyncio
async def test_value_and_feature_setup_sync_async_parity():
    sync, asynchronous = Mock(), Mock()
    sync.post.return_value = {"execution_permitted": False}
    asynchronous.post = AsyncMock(return_value={"execution_permitted": False})
    values = dict(context_schema={"version": "v1", "fields": {}},
        actions={"a": {"risk_tier": "high"}},
        configuration={"schema_version": "outcome-policy-v3", "contextual_model": "linear_optional"},
        value_objective={"success_value": 10, "max_cost": 20, "cost_unit": "USD"})
    assert SyncProofLoopResource(sync).setup_policy("p", **values) == await ProofLoopResource(asynchronous).setup_policy("p", **values)
    assert sync.post.call_args == asynchronous.post.call_args
    body = sync.post.call_args.kwargs["json"]
    assert body["configuration"]["actions"] == values["actions"]
    assert body["value_objective"] == values["value_objective"]
