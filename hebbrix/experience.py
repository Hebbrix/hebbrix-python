"""Opt-in binding of a revalidated lesson context to an exact actor request.

This is a caller-side audit boundary, not remote attestation, memory truth,
causal credit, or execution permission. No provider is selected or called
automatically. Supply a transport that sends the supplied JSON bytes unchanged.
Authorization headers must be supplied separately by that transport.
"""

# Public SDK still supports Python 3.8; retain compatible typing annotations.
# ruff: noqa: UP006, UP007, UP035

import hashlib
import json
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Sequence, Union


def _json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _time(value: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError("experience assessment timestamp is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("experience assessment timestamp must include timezone")
    return parsed


class ExperienceRequest:
    """Seal a complete model request containing the exact untrusted context.

    `context_path` identifies the one JSON object or JSON-string field containing
    the returned context, e.g. ("input", 1, "content"). It must not insert memory
    into system/developer instructions. The caller still controls action
    authorization and must keep model outputs outside privileged execution.

    An instance dispatches at most once, including a timeout. Retrying an
    uncertain provider request needs explicit reconciliation/new attempt, not
    an automatic repeat. A fresh server assessment is required for a new use.
    """

    def __init__(
        self,
        *,
        response: Dict[str, Any],
        request: Dict[str, Any],
        context_path: Sequence[Union[str, int]],
        expected_scope: Dict[str, Any],
        target_context: Dict[str, Any],
        model_name: str,
        model_version: str,
        max_age_seconds: int = 30,
    ):
        if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 60:
            raise ValueError("invalid experience assessment age bound")
        if not all(
            isinstance(s, str) and s.strip() and len(s) <= 160
            for s in (model_name, model_version)
        ):
            raise ValueError("explicit model identity required")
        # Take independent JSON snapshots before validation; later mutation of
        # caller dictionaries must not change a dispatched payload or receipt.
        response = json.loads(_json(response))
        body = _json(request)
        if len(body) > 2_000_000:
            raise ValueError("experience actor request exceeds byte bound")
        request = json.loads(body)
        context = response.get("context")
        if (
            not isinstance(context, dict)
            or context.get("schema_version") != "experience-context-v1"
        ):
            raise ValueError("unsupported experience context")
        if (
            response.get("context_digest") != _digest(context)
            or _json(context.get("scope")) != _json(expected_scope)
            or context.get("target_context_digest") != _digest(target_context)
        ):
            raise ValueError("experience context integrity or scope mismatch")
        if (
            response.get("authorization_granted") is not False
            or context.get("authorization_granted") is not False
            or response.get("actor_exposure_verified") is not False
            or response.get("revalidation_required") is not True
        ):
            raise ValueError("experience context must not claim authority or exposure")
        lessons = context.get("lessons")
        if (
            not isinstance(lessons, list)
            or len(lessons) > 20
            or response.get("no_match") is not (not lessons)
        ):
            raise ValueError("inconsistent experience selection")
        references = []
        ids = set()
        for lesson in lessons:
            if (
                not isinstance(lesson, dict)
                or lesson.get("trust") != "untrusted_experience_hypothesis"
                or lesson.get("authorization_granted") is not False
                or lesson.get("lesson_truth_verified") is not False
            ):
                raise ValueError(
                    "experience lesson must remain an untrusted hypothesis"
                )
            ident, checksum = lesson.get("memory_id"), lesson.get("record_digest")
            if (
                not isinstance(ident, str)
                or not 1 <= len(ident) <= 36
                or ident in ids
                or not isinstance(checksum, str)
                or len(checksum) != 64
                or any(c not in "0123456789abcdef" for c in checksum)
            ):
                raise ValueError("invalid or duplicate experience reference")
            ids.add(ident)
            references.append(
                {
                    "kind": "memory",
                    "reference_id": ident,
                    "digest": "sha256:" + checksum,
                    "role": "supporting",
                }
            )
        if (
            not isinstance(context_path, (list, tuple))
            or not 1 <= len(context_path) <= 16
        ):
            raise ValueError("explicit bounded context location required")
        located = request
        for part in context_path:
            if isinstance(located, dict) and located.get("role") in {
                "system",
                "developer",
            }:
                raise ValueError("memory cannot be promoted to privileged instructions")
            if type(part) is str and isinstance(located, dict):
                if (
                    part in {"instructions", "system", "developer"}
                    or part not in located
                ):
                    raise ValueError("invalid or privileged context location")
            elif type(part) is int and isinstance(located, list):
                if not 0 <= part < len(located):
                    raise ValueError("invalid context location index")
            else:
                raise ValueError("context location type mismatch")
            located = located[part]
        if isinstance(located, str):
            located = json.loads(located)
        if _json(located) != _json(context):
            raise ValueError(
                "actor request does not contain the exact experience context"
            )
        self._body = body
        self._assessed_at = _time(response.get("assessed_at"))
        self._max_age = max_age_seconds
        self._lock = threading.Lock()
        self._attempted = False
        self._manifest = _json(
            {
                "schema_version": "proofloop-evidence-v1",
                "references": references,
                "model": {"name": model_name, "version": model_version},
                "prompt": {
                    "name": "caller.experience.request",
                    "version": "v1",
                    "digest": "sha256:" + hashlib.sha256(body).hexdigest(),
                },
                "tools": [
                    {
                        "name": "hebbrix.experience.context",
                        "version": "v1",
                        "digest": "sha256:" + response["context_digest"],
                    }
                ],
            }
        )
        self._fresh()

    def _fresh(self):
        age = (datetime.now(timezone.utc) - self._assessed_at).total_seconds()
        if age < -5 or age > self._max_age:
            raise ValueError(
                "experience assessment is stale; revalidate before dispatch"
            )

    def _begin(self):
        with self._lock:
            if self._attempted:
                raise RuntimeError(
                    "experience request already attempted; reconcile before retry"
                )
            self._fresh()
            self._attempted = True

    def dispatch(self, send_json_bytes: Callable[[bytes], Any]) -> Any:
        """Invoke the caller's provider transport once; no silent retry/fallback."""
        self._begin()
        return send_json_bytes(self._body)

    async def dispatch_async(self, send_json_bytes: Callable[[bytes], Any]) -> Any:
        """Async equivalent, retaining the same uncertain-delivery boundary."""
        self._begin()
        return await send_json_bytes(self._body)

    def evidence_manifest(self) -> Dict[str, Any]:
        """Client-declared manifest for proofloop.decide(evidence_manifest=...).

        Binding is to the entire sealed request, not just search hits. This
        cannot attest that the provider consumed it or that a memory caused
        the chosen action. Do not combine it with a prior proof_context_token.
        """
        return json.loads(self._manifest)

    def audit_metadata(self) -> Dict[str, Any]:
        return {
            "schema_version": "caller-experience-request-v1",
            "request_digest": hashlib.sha256(self._body).hexdigest(),
            "request_bytes": len(self._body),
            "dispatch_attempted": self._attempted,
            "assurance": "caller_boundary_not_remote_attestation",
            "provider_consumption_verified": False,
            "causal_memory_credit": False,
            "authorization_granted": False,
        }
