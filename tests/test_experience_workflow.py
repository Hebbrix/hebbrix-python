"""Provider-neutral worker boundary; no paid calls in these regressions."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from hebbrix.experience import _digest
from hebbrix.workflow import (
    AsyncExperienceWorkflow,
    AsyncReflectionWorker,
    ExperienceWorkflow,
    ReflectionResult,
    ReflectionUncertain,
    ReflectionWorker,
)


def fixture():
    source = {
        "schema_version": "experience-reflection-input-v1",
        "model": "pinned-model",
        "authorization_granted": False,
        "required_features": [{"key": "stateful", "value": True}],
    }
    return {
        "job_id": "job",
        "input": source,
        "input_digest": _digest(source),
        "status": "claimed",
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat(),
    }


def prepare(source):
    return {
        "model": source["model"],
        "input": [{"role": "user", "content": json.dumps(source)}],
    }, ("input", 0, "content")


def result():
    return ReflectionResult(
        output={
            "hypotheses": [],
            "insufficient_evidence_reason": "No diagnostic evidence",
        },
        raw_response=b'{"result":"source-limited"}',
        reported_microusd=12,
    )


class Workflow:
    def __init__(self, failure=None):
        self.row, self.failure, self.sent = fixture(), failure, []

    def claim(self, *args, **kwargs):
        return {"job": dict(self.row)}

    def dispatch(self, job_id, **kwargs):
        assert self.row["status"] == "claimed"
        self.row.update(status="dispatched", request_digest=kwargs["request_digest"])
        if self.failure == "dispatch":
            raise TimeoutError("must not leak provider detail")
        return {
            "job": dict(self.row),
            "model_dispatch_allowed": True,
            "automatic_retry_allowed": False,
        }

    def complete(self, job_id, **payload):
        if self.failure == "complete":
            raise TimeoutError("unknown delivery")
        self.sent.append(payload)
        self.row["status"] = "completed"
        return {"job": dict(self.row)}

    def uncertain(self, job_id, **payload):
        self.row["status"] = "unknown"
        self.sent.append(payload)


def test_worker_seals_complete_request_and_does_not_redispatch_on_resume():
    workflow, captured = Workflow(), []
    worker = ReflectionWorker(workflow)

    def send(body):
        captured.append(body)
        return result()

    done = worker.run_once(
        "program", request_key="same", prepare=prepare, send_json_bytes=send
    )
    assert done["job"]["status"] == "completed" and len(captured) == 1
    assert (
        json.loads(json.loads(captured[0])["input"][0]["content"]) == fixture()["input"]
    )
    worker.run_once(
        "program", request_key="same", prepare=prepare, send_json_bytes=send
    )
    assert len(captured) == 1
    assert (
        workflow.sent[0]["provider_response_digest"]
        and workflow.sent[0]["reported_microusd"] == 12
    )


@pytest.mark.parametrize("stage", ["dispatch", "provider", "output", "complete"])
def test_uncertain_request_is_never_automatically_repeated(stage):
    workflow, captured = Workflow(stage), []

    def send(body):
        captured.append(body)
        if stage == "provider":
            raise TimeoutError("secret must not escape")
        return None if stage == "output" else result()

    worker = ReflectionWorker(workflow)
    with pytest.raises(ReflectionUncertain) as raised:
        worker.run_once("p", request_key="k", prepare=prepare, send_json_bytes=send)
    error = raised.value
    assert "secret" not in str(error) and error.job_id == "job"
    assert bool(error.completion_payload) is (stage == "complete")
    assert len(captured) == (0 if stage == "dispatch" else 1)
    worker.run_once("p", request_key="k", prepare=prepare, send_json_bytes=send)
    assert len(captured) == (0 if stage == "dispatch" else 1)


@pytest.mark.parametrize(
    "mutation", ["input", "model", "privileged", "removed", "size"]
)
def test_adapters_cannot_change_source_or_owner_model(mutation):
    workflow = Workflow()

    def invalid(source):
        if mutation == "input":
            source["authorization_granted"] = True
        body, path = prepare(source)
        if mutation == "model":
            body["model"] = "unapproved-model"
        if mutation == "privileged":
            body["input"][0]["role"] = "system"
        if mutation == "removed":
            body["input"][0]["content"] = "{}"
        if mutation == "size":
            body["padding"] = "x" * 256001
        return body, path

    with pytest.raises(ValueError):
        ReflectionWorker(workflow).run_once(
            "p",
            request_key="k",
            prepare=invalid,
            send_json_bytes=lambda _: pytest.fail("must not call provider"),
        )
    assert workflow.row["status"] == "claimed"


@pytest.mark.asyncio
async def test_async_worker_has_the_same_one_attempt_contract():
    sync = Workflow()

    class AsyncWorkflow:
        async def claim(self, *args, **kwargs):
            return sync.claim(*args, **kwargs)

        async def dispatch(self, *args, **kwargs):
            return sync.dispatch(*args, **kwargs)

        async def complete(self, *args, **kwargs):
            return sync.complete(*args, **kwargs)

        async def uncertain(self, *args, **kwargs):
            return sync.uncertain(*args, **kwargs)

    seen = []

    async def send(body):
        seen.append(body)
        return result()

    worker = AsyncReflectionWorker(AsyncWorkflow())
    assert (
        await worker.run_once(
            "p", request_key="k", prepare=prepare, send_json_bytes=send
        )
    )["job"]["status"] == "completed"
    await worker.run_once("p", request_key="k", prepare=prepare, send_json_bytes=send)
    assert len(seen) == 1


def test_sync_resource_quotes_opaque_ids_and_preserves_state_fields():
    class Client:
        def __init__(self):
            self.calls = []

        def get(self, path, **kwargs):
            self.calls.append(("GET", path, kwargs))
            return {"current": True}

        def post(self, path, **kwargs):
            self.calls.append(("POST", path, kwargs))
            return {"authorization_granted": False}

    client = Client()
    resource = ExperienceWorkflow(client)
    resource.dispatch("a/b", input_digest="a" * 64, request_digest="b" * 64)
    assert client.calls[0][1].endswith("/jobs/a%2Fb/dispatch")
    assert (
        resource.review("a/b", expected_sequence=0, expected_digest=None)[
            "authorization_granted"
        ]
        is False
    )
    resource.review_queue("a/b", after_id="old", limit=5)
    assert client.calls[-1][2]["params"] == {"after_id": "old", "limit": 5}
    resource.revise("l/x", request_key="revision", expected_sequence=1)
    assert client.calls[-1] == (
        "POST",
        "/v1/learning/experiences/lessons/l%2Fx/revisions",
        {"json": {"request_key": "revision", "expected_sequence": 1}},
    )


@pytest.mark.asyncio
async def test_async_resource_preserves_completion_and_uncertainty():
    class Client:
        async def post(self, path, **kwargs):
            return {"path": path, **kwargs}

    resource = AsyncExperienceWorkflow(Client())
    value = await resource.complete(
        "a/b", output={"hypotheses": []}, reported_microusd=12
    )
    assert (
        value["path"].endswith("/jobs/a%2Fb/complete")
        and value["json"]["reported_microusd"] == 12
    )
    value = await resource.uncertain(
        "a/b", request_digest="c" * 64, reason="provider_failure"
    )
    assert value["json"]["reason"] == "provider_failure"
    value = await resource.revise("l/x", request_key="revision", expected_sequence=1)
    assert value["path"].endswith("/lessons/l%2Fx/revisions")
    assert value["json"]["expected_sequence"] == 1
