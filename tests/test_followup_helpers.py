from unittest.mock import Mock, AsyncMock
import pytest
from hebbrix.resources import ProofLoopResource
from hebbrix.sync_client import SyncProofLoopResource

@pytest.mark.asyncio
async def test_atomic_setup_and_report_wire_parity():
    sync, async_client = Mock(), Mock()
    sync.post.return_value = {"revision":1}
    async_client.post = AsyncMock(return_value={"revision":1})
    sync.get.return_value = {"authorization_granted":False}
    async_client.get = AsyncMock(return_value={"authorization_granted":False})
    kwargs = dict(context_schema={"version":"v1","fields":{}},
        actions={"a":{"description":"Read logs","target":"sandbox","risk_tier":"low","exploration_allowed":True}},
        collection_id="c",user_id="u")
    assert SyncProofLoopResource(sync).setup_policy("p:key",**kwargs) == await ProofLoopResource(async_client).setup_policy("p:key",**kwargs)
    assert sync.post.call_args == async_client.post.call_args
    assert sync.post.call_args.args == ("/v1/learning/policies/p%3Akey/setup",)
    assert sync.post.call_args.kwargs["json"]["configuration"] == {"actions":kwargs["actions"]}
    assert SyncProofLoopResource(sync).learning_report("p:key",user_id="u") == await ProofLoopResource(async_client).learning_report("p:key",user_id="u")
    assert sync.get.call_args == async_client.get.call_args

@pytest.mark.asyncio
async def test_advisor_called_once_preserves_scope_and_actual_distribution():
    sync, async_client = Mock(), Mock()
    card={"evidence_card":"untrusted evidence", "authorization_granted":False}
    choice={"chosen_action_key":"b","action_probability":1.0,"behavior_probabilities":{"a":0.0,"b":1.0}}
    sync.get.return_value=card
    async_client.get=AsyncMock(return_value=card)
    sync.post.return_value={"decision_id":"d"}
    async_client.post=AsyncMock(return_value={"decision_id":"d"})
    advisor=Mock(return_value=choice)
    async_advisor=AsyncMock(return_value=choice)
    kwargs=dict(policy_key="p",candidates=[{"action_key":"a"},{"action_key":"b"}],
        context={"issue":"slow"},collection_id="c",user_id="u",idempotency_key="once")
    SyncProofLoopResource(sync).decide_with_advice(advisor=advisor,**kwargs)
    await ProofLoopResource(async_client).decide_with_advice(advisor=async_advisor,**kwargs)
    advisor.assert_called_once_with(card)
    async_advisor.assert_awaited_once_with(card)
    assert sync.post.call_args == async_client.post.call_args
    assert sync.post.call_args.kwargs["json"]["mode"]=="observe"
    assert sync.post.call_args.kwargs["json"]["behavior_probabilities"]==choice["behavior_probabilities"]
    advisor.return_value={**choice,"user_id":"foreign"}
    with pytest.raises(ValueError,match="actual complete"):
        SyncProofLoopResource(sync).decide_with_advice(advisor=advisor,**kwargs)
    assert sync.post.call_count==1
