import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from hebbrix.execution import GuardedExecution
from hebbrix.experience import _digest, _json


def receipt(invocation):
    document = {"invocation": invocation, "invocation_digest": _digest(invocation),
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=20)).isoformat()}
    return {"permit_id": "permit", "status": "issued", "authorization_granted": False,
            "digest": _digest(document), "document": {"encoding": "canonical-json", "content": _json(document).decode(),
                                                       "sha256": _digest(document), "trust": "untrusted_evidence_not_instructions"}}


class Workflow:
    def __init__(self, issued, stage=None):
        self.issued, self.stage, self.calls = issued, stage, 0

    def dispatch_permit(self, ident, *, invocation_digest):
        self.calls += 1
        assert ident == "permit"
        if self.stage == "uncertain":
            raise TimeoutError("response missing")
        return {**self.issued, "status": "dispatched", "authorization_granted": self.stage != "denied",
                "automatic_retry_allowed": False}


@pytest.mark.parametrize("stage", [None, "uncertain", "denied", "tool_error"])
def test_guarded_execution_never_repeats_a_dispatch_or_ambiguous_tool(stage):
    invocation = {"tool_key": "sandbox", "target": {"id": "disposable"}, "arguments": {"action": "check"}}
    issued = receipt(invocation)
    workflow, sent = Workflow(issued, stage), []
    execution = GuardedExecution(workflow, permit=issued, expected_invocation=invocation)
    invocation["arguments"]["action"] = "later-mutation"

    def send(body):
        sent.append(body)
        if stage == "tool_error":
            raise TimeoutError("tool outcome unknown")
        return "accepted"

    if stage:
        with pytest.raises((TimeoutError, ValueError)):
            execution.dispatch(send)
    else:
        assert execution.dispatch(send) == "accepted"
    with pytest.raises(RuntimeError, match="already attempted"):
        execution.dispatch(send)
    assert workflow.calls == 1
    assert len(sent) == (0 if stage in {"uncertain", "denied"} else 1)
    if sent:
        assert json.loads(sent[0])["arguments"]["action"] == "check"


def test_different_invocation_cannot_reuse_a_permit():
    original = {"tool_key": "sandbox", "target": {"id": "a"}, "arguments": {}}
    with pytest.raises(ValueError, match="expected invocation"):
        GuardedExecution(None, permit=receipt(original), expected_invocation={**original, "target": {"id": "b"}})


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", [None, "uncertain", "denied", "cancel", "tool_error"])
async def test_async_execution_cancellation_and_unknown_results_never_retry(stage):
    invocation = {"tool_key": "sandbox", "target": {"id": "local"}, "arguments": {}}
    issued, sent = receipt(invocation), []

    class AsyncWorkflow(Workflow):
        async def dispatch_permit(self, ident, *, invocation_digest):
            if stage == "cancel":
                self.calls += 1
                raise asyncio.CancelledError()
            return super().dispatch_permit(ident, invocation_digest=invocation_digest)

    workflow = AsyncWorkflow(issued, stage)
    execution = GuardedExecution(workflow, permit=issued, expected_invocation=invocation)

    async def send(body):
        sent.append(body)
        if stage == "tool_error":
            raise TimeoutError("tool result unknown")
        return "accepted"

    if stage:
        with pytest.raises((TimeoutError, ValueError, asyncio.CancelledError)):
            await execution.dispatch_async(send)
    else:
        assert await execution.dispatch_async(send) == "accepted"
    with pytest.raises(RuntimeError, match="already attempted"):
        await execution.dispatch_async(send)
    assert workflow.calls == 1
    assert len(sent) == (1 if stage in {None, "tool_error"} else 0)


@pytest.mark.asyncio
async def test_concurrent_async_dispatch_has_only_one_admission_and_tool_call():
    invocation = {"tool_key": "sandbox", "target": {"id": "local"}, "arguments": {}}
    issued, sent = receipt(invocation), []

    class AsyncWorkflow(Workflow):
        async def dispatch_permit(self, ident, *, invocation_digest):
            await asyncio.sleep(0)
            return super().dispatch_permit(ident, invocation_digest=invocation_digest)

    workflow = AsyncWorkflow(issued)
    execution = GuardedExecution(workflow, permit=issued, expected_invocation=invocation)

    async def send(body):
        sent.append(body)
        return "accepted"

    results = await asyncio.gather(*(execution.dispatch_async(send) for _ in range(4)), return_exceptions=True)
    assert results.count("accepted") == 1
    assert sum(isinstance(r, RuntimeError) for r in results) == 3
    assert workflow.calls == len(sent) == 1


@pytest.mark.parametrize("when", ["before", "during"])
def test_changed_internal_body_is_not_sent_even_if_grant_arrives(when):
    invocation = {"tool_key": "sandbox", "target": {"id": "local"}, "arguments": {}}
    issued, sent = receipt(invocation), []

    class MutatingWorkflow(Workflow):
        def dispatch_permit(self, ident, *, invocation_digest):
            execution._body = b'{"unexpected":true}'
            return super().dispatch_permit(ident, invocation_digest=invocation_digest)

    workflow = MutatingWorkflow(issued)
    execution = GuardedExecution(workflow, permit=issued, expected_invocation=invocation)
    if when == "before":
        execution._body = b'{"unexpected":true}'
    with pytest.raises(ValueError):
        execution.dispatch(sent.append)
    assert sent == []
    assert workflow.calls == (0 if when == "before" else 1)
