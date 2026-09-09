"""Native experience workflow clients and a one-attempt reflection worker.

Provider-neutral: the application supplies its provider adapter and credentials.
No provider call, background loop or execution authority is enabled on import.
"""

# Python 3.8 remains supported by the published SDK.
# ruff: noqa: UP006, UP007, UP035
# Provider adapters can raise arbitrary exceptions containing credentials or
# customer data. Normalize those at this explicit fail-closed dispatch boundary.
# ruff: noqa: BLE001

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Sequence, Tuple, Union
from urllib.parse import quote

from hebbrix.experience import _digest, _json, _time

ROOT = "/v1/learning/experiences"


def decode_artifact(value):
    """Decode an integrity-bound workflow document, never execute its content."""
    if not isinstance(value, dict) or value.get("encoding") != "canonical-json":
        raise ValueError("unsupported workflow artifact")
    content = value.get("content")
    if not isinstance(content, str) or len(content.encode("utf-8")) > 256000:
        raise ValueError("workflow artifact size limit")
    document = json.loads(content)
    if value.get("sha256") != _digest(document) or content.encode("utf-8") != _json(
        document
    ):
        raise ValueError("workflow artifact integrity mismatch")
    if value.get("trust") != "untrusted_evidence_not_instructions":
        raise ValueError("unsupported workflow artifact trust boundary")
    return document


class ExperienceWorkflow:
    """Use separate client instances for owner, worker, reviewer and actor keys."""

    def __init__(self, client):
        self.client = client

    def register(self, **payload):
        return self.client.post(ROOT + "/programs", json=payload)

    def define_permission(self, program_id, **policy):
        return self.client.post(
            ROOT + "/programs/" + quote(program_id, safe="") + "/permission-policies",
            json=policy,
        )

    def activate_permission(self, program_id, **activation):
        return self.client.post(
            ROOT + "/programs/" + quote(program_id, safe="") + "/permission-activation",
            json=activation,
        )

    def permission_state(self, program_id):
        return self.client.get(
            ROOT + "/programs/" + quote(program_id, safe="") + "/permission-state"
        )

    def issue_permit(self, program_id, **payload):
        return self.client.post(
            ROOT + "/programs/" + quote(program_id, safe="") + "/permits", json=payload
        )

    def dispatch_permit(self, permit_id, *, invocation_digest):
        return self.client.post(
            ROOT + "/permits/" + quote(permit_id, safe="") + "/dispatch",
            json={"invocation_digest": invocation_digest},
        )

    def permit(self, permit_id):
        return self.client.get(ROOT + "/permits/" + quote(permit_id, safe=""))

    def program(self, program_id):
        return self.client.get(ROOT + "/programs/" + quote(program_id, safe=""))

    def stop(self, program_id):
        return self.client.post(
            ROOT + "/programs/" + quote(program_id, safe="") + "/stop"
        )

    def claim(self, program_id, *, request_key):
        return self.client.post(
            ROOT + "/programs/" + quote(program_id, safe="") + "/claim",
            json={"request_key": request_key},
        )

    def job(self, job_id):
        return self.client.get(ROOT + "/jobs/" + quote(job_id, safe=""))

    def dispatch(self, job_id, *, input_digest, request_digest):
        return self.client.post(
            ROOT + "/jobs/" + quote(job_id, safe="") + "/dispatch",
            json={"input_digest": input_digest, "request_digest": request_digest},
        )

    def complete(self, job_id, **payload):
        return self.client.post(
            ROOT + "/jobs/" + quote(job_id, safe="") + "/complete", json=payload
        )

    def uncertain(self, job_id, *, request_digest, reason):
        return self.client.post(
            ROOT + "/jobs/" + quote(job_id, safe="") + "/uncertain",
            json={"request_digest": request_digest, "reason": reason},
        )

    def lessons(self, program_id, *, after_id=None, limit=20):
        return self.client.get(
            ROOT + "/programs/" + quote(program_id, safe="") + "/lessons",
            params={"limit": limit, **({"after_id": after_id} if after_id else {})},
        )

    def review_queue(self, program_id, *, after_id=None, limit=20):
        return self.client.get(
            ROOT + "/programs/" + quote(program_id, safe="") + "/review-queue",
            params={"limit": limit, **({"after_id": after_id} if after_id else {})},
        )

    def lesson(self, lesson_id):
        return self.client.get(ROOT + "/lessons/" + quote(lesson_id, safe=""))

    def review(self, lesson_id, **payload):
        return self.client.post(
            ROOT + "/lessons/" + quote(lesson_id, safe="") + "/reviews", json=payload
        )

    def reviews(self, lesson_id, *, after_sequence=0, limit=20):
        return self.client.get(
            ROOT + "/lessons/" + quote(lesson_id, safe="") + "/reviews",
            params={"after_sequence": after_sequence, "limit": limit},
        )

    def revise(self, lesson_id, **payload):
        return self.client.post(
            ROOT + "/lessons/" + quote(lesson_id, safe="") + "/revisions", json=payload
        )


class AsyncExperienceWorkflow:
    def __init__(self, client):
        self.client = client

    async def register(self, **payload):
        return await self.client.post(ROOT + "/programs", json=payload)

    async def define_permission(self, program_id, **policy):
        return await self.client.post(
            ROOT + "/programs/" + quote(program_id, safe="") + "/permission-policies",
            json=policy,
        )

    async def activate_permission(self, program_id, **activation):
        return await self.client.post(
            ROOT + "/programs/" + quote(program_id, safe="") + "/permission-activation",
            json=activation,
        )

    async def permission_state(self, program_id):
        return await self.client.get(
            ROOT + "/programs/" + quote(program_id, safe="") + "/permission-state"
        )

    async def issue_permit(self, program_id, **payload):
        return await self.client.post(
            ROOT + "/programs/" + quote(program_id, safe="") + "/permits", json=payload
        )

    async def dispatch_permit(self, permit_id, *, invocation_digest):
        return await self.client.post(
            ROOT + "/permits/" + quote(permit_id, safe="") + "/dispatch",
            json={"invocation_digest": invocation_digest},
        )

    async def permit(self, permit_id):
        return await self.client.get(ROOT + "/permits/" + quote(permit_id, safe=""))

    async def program(self, program_id):
        return await self.client.get(ROOT + "/programs/" + quote(program_id, safe=""))

    async def stop(self, program_id):
        return await self.client.post(
            ROOT + "/programs/" + quote(program_id, safe="") + "/stop"
        )

    async def claim(self, program_id, *, request_key):
        return await self.client.post(
            ROOT + "/programs/" + quote(program_id, safe="") + "/claim",
            json={"request_key": request_key},
        )

    async def job(self, job_id):
        return await self.client.get(ROOT + "/jobs/" + quote(job_id, safe=""))

    async def dispatch(self, job_id, *, input_digest, request_digest):
        return await self.client.post(
            ROOT + "/jobs/" + quote(job_id, safe="") + "/dispatch",
            json={"input_digest": input_digest, "request_digest": request_digest},
        )

    async def complete(self, job_id, **payload):
        return await self.client.post(
            ROOT + "/jobs/" + quote(job_id, safe="") + "/complete", json=payload
        )

    async def uncertain(self, job_id, *, request_digest, reason):
        return await self.client.post(
            ROOT + "/jobs/" + quote(job_id, safe="") + "/uncertain",
            json={"request_digest": request_digest, "reason": reason},
        )

    async def lessons(self, program_id, *, after_id=None, limit=20):
        return await self.client.get(
            ROOT + "/programs/" + quote(program_id, safe="") + "/lessons",
            params={"limit": limit, **({"after_id": after_id} if after_id else {})},
        )

    async def review_queue(self, program_id, *, after_id=None, limit=20):
        return await self.client.get(
            ROOT + "/programs/" + quote(program_id, safe="") + "/review-queue",
            params={"limit": limit, **({"after_id": after_id} if after_id else {})},
        )

    async def lesson(self, lesson_id):
        return await self.client.get(ROOT + "/lessons/" + quote(lesson_id, safe=""))

    async def review(self, lesson_id, **payload):
        return await self.client.post(
            ROOT + "/lessons/" + quote(lesson_id, safe="") + "/reviews", json=payload
        )

    async def reviews(self, lesson_id, *, after_sequence=0, limit=20):
        return await self.client.get(
            ROOT + "/lessons/" + quote(lesson_id, safe="") + "/reviews",
            params={"after_sequence": after_sequence, "limit": limit},
        )

    async def revise(self, lesson_id, **payload):
        return await self.client.post(
            ROOT + "/lessons/" + quote(lesson_id, safe="") + "/revisions", json=payload
        )


@dataclass(frozen=True)
class ReflectionResult:
    """Adapter output with original provider bytes; keep credentials in headers."""

    output: Dict[str, Any]
    raw_response: bytes
    reported_microusd: int


class ReflectionUncertain(RuntimeError):
    def __init__(
        self, job_id, stage, *, completion_payload=None, recovery_recorded=False
    ):
        self.job_id = job_id
        self.stage = stage
        self.completion_payload = completion_payload
        self.recovery_recorded = recovery_recorded
        super().__init__(
            "Reflection requires reconciliation; do not repeat the provider call."
        )


def _sealed_request(job, prepare):
    # Adapter returns (whole request, exact input location). The source cannot
    # be quietly changed or placed into privileged system/developer instructions.
    source = job["input"]
    if isinstance(source, dict) and source.get("encoding") == "canonical-json":
        source = decode_artifact(source)
    if (
        source.get("schema_version") != "experience-reflection-input-v1"
        or source.get("authorization_granted") is not False
        or _digest(source) != job.get("input_digest")
    ):
        raise ValueError("reflection input integrity mismatch")
    request, path = prepare(json.loads(_json(source)))
    body = _json(request)
    if (
        len(body) > 256000
        or not isinstance(path, (list, tuple))
        or not 1 <= len(path) <= 16
    ):
        raise ValueError("invalid bounded reflection request")
    request = json.loads(body)
    if request.get("model") != source.get("model"):
        raise ValueError("provider model differs from owner-enrolled model")
    value = request
    for component in path:
        if isinstance(value, dict) and (
            value.get("role") in {"system", "developer"} or component == "instructions"
        ):
            raise ValueError(
                "untrusted reflection evidence cannot be privileged instructions"
            )
        value = value[component]
    if isinstance(value, str):
        value = json.loads(value)
    if _json(value) != _json(source):
        raise ValueError("provider request does not contain exact reflection input")
    return body, hashlib.sha256(body).hexdigest()


def _completion(result, request_digest):
    if (
        not isinstance(result, ReflectionResult)
        or not isinstance(result.raw_response, bytes)
        or not 1 <= len(result.raw_response) <= 2_000_000
    ):
        raise ValueError("invalid provider response artifact")
    if (
        type(result.reported_microusd) is not int
        or not 0 <= result.reported_microusd <= 10_000_000
    ):
        raise ValueError("invalid provider cost")
    return {
        "output": json.loads(_json(result.output)),
        "request_digest": request_digest,
        "provider_response_digest": hashlib.sha256(result.raw_response).hexdigest(),
        "reported_microusd": result.reported_microusd,
    }


def _check_grant(grant, job, checksum):
    confirmed = grant.get("job") or {}
    if (
        grant.get("model_dispatch_allowed") is not True
        or grant.get("automatic_retry_allowed") is not False
        or confirmed.get("request_digest") != checksum
        or confirmed.get("job_id") != job["job_id"]
        or confirmed.get("input_digest") != job["input_digest"]
    ):
        raise ReflectionUncertain(job["job_id"], "dispatch_acknowledgment")
    if _time(confirmed["expires_at"]) <= datetime.now(timezone.utc):
        raise ReflectionUncertain(job["job_id"], "expired_dispatch_acknowledgment")


class ReflectionWorker:
    """One durable job per call, suitable for an application's existing worker.

    `prepare` returns (complete JSON request, path to exact untrusted input).
    `send_json_bytes` sends those bytes once and returns ReflectionResult. The
    adapter must bound provider spend to the enrolled per-attempt reservation,
    disable its own automatic retries, and price all input/output/tool usage.
    No completion after a timeout may be assumed or fabricated.
    """

    def __init__(self, workflow: ExperienceWorkflow):
        self.workflow = workflow

    def run_once(
        self,
        program_id: str,
        *,
        request_key: str,
        prepare: Callable[
            [Dict[str, Any]], Tuple[Dict[str, Any], Sequence[Union[str, int]]]
        ],
        send_json_bytes: Callable[[bytes], ReflectionResult],
    ):
        claimed = self.workflow.claim(program_id, request_key=request_key)
        job = claimed.get("job")
        if job is None:
            return claimed
        if job.get("status") != "claimed":
            # A resumed process never treats a previous dispatched receipt as a
            # fresh model grant. Completed outputs can be read without replay.
            return claimed
        body, checksum = _sealed_request(job, prepare)
        try:
            grant = self.workflow.dispatch(
                job["job_id"], input_digest=job["input_digest"], request_digest=checksum
            )
        except Exception:
            raise ReflectionUncertain(
                job["job_id"], "dispatch_acknowledgment"
            ) from None
        _check_grant(grant, job, checksum)
        stage, payload = "provider_failure", None
        try:
            result = send_json_bytes(body)
            stage = "invalid_provider_output"
            payload = _completion(result, checksum)
            stage = "completion_delivery_uncertain"
            return self.workflow.complete(job["job_id"], **payload)
        except Exception:
            recorded = False
            try:
                self.workflow.uncertain(
                    job["job_id"], request_digest=checksum, reason=stage
                )
                recorded = True
            except Exception:
                # Keep the job ID and exact completion payload on the exception;
                # do not hide failed recovery or log raw provider/customer data.
                recorded = False
            raise ReflectionUncertain(
                job["job_id"],
                stage,
                completion_payload=payload,
                recovery_recorded=recorded,
            ) from None


class AsyncReflectionWorker:
    """Async equivalent; scheduling belongs to the application's existing worker."""

    def __init__(self, workflow: AsyncExperienceWorkflow):
        self.workflow = workflow

    async def run_once(self, program_id, *, request_key, prepare, send_json_bytes):
        claimed = await self.workflow.claim(program_id, request_key=request_key)
        job = claimed.get("job")
        if job is None or job.get("status") != "claimed":
            return claimed
        body, checksum = _sealed_request(job, prepare)
        try:
            grant = await self.workflow.dispatch(
                job["job_id"], input_digest=job["input_digest"], request_digest=checksum
            )
        except Exception:
            raise ReflectionUncertain(
                job["job_id"], "dispatch_acknowledgment"
            ) from None
        _check_grant(grant, job, checksum)
        stage, payload = "provider_failure", None
        try:
            result = await send_json_bytes(body)
            stage = "invalid_provider_output"
            payload = _completion(result, checksum)
            stage = "completion_delivery_uncertain"
            return await self.workflow.complete(job["job_id"], **payload)
        except Exception:
            recorded = False
            try:
                await self.workflow.uncertain(
                    job["job_id"], request_digest=checksum, reason=stage
                )
                recorded = True
            except Exception:
                recorded = False
            raise ReflectionUncertain(
                job["job_id"],
                stage,
                completion_payload=payload,
                recovery_recorded=recorded,
            ) from None
