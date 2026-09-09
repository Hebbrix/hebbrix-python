"""One-use client admission for a caller-managed, constrained tool adapter.

Not a sandbox: the application must implement the owner-approved capability,
bind the exact target descriptor to its real resource and withhold other tools.
No command, network action or infrastructure operation is supplied by this SDK.
"""

import threading
from datetime import datetime, timezone

from hebbrix.experience import _digest, _json, _time
from hebbrix.workflow import decode_artifact


class GuardedExecution:
    def __init__(self, workflow, *, permit, expected_invocation):
        self.workflow = workflow
        self._permit_id = permit.get("permit_id")
        self._body = _json(expected_invocation)
        self._document = decode_artifact(permit["document"])
        self._document_digest = _digest(self._document)
        if (
            not self._permit_id
            or permit.get("authorization_granted") is not False
            or permit.get("status") != "issued"
            or permit.get("digest") != self._document_digest
            or self._document.get("invocation_digest") != _digest(expected_invocation)
            or _json(self._document.get("invocation")) != self._body
            or _time(self._document["expires_at"]) <= datetime.now(timezone.utc)
        ):
            raise ValueError("permit does not match the expected invocation")
        self._lock, self._attempted = threading.Lock(), False

    def _begin(self):
        with self._lock:
            if self._attempted:
                raise RuntimeError(
                    "execution already attempted; reconcile instead of retrying"
                )
            self._attempted = True  # Lost acknowledgement must not run a tool.
            if (
                _digest(self._document) != self._document_digest
                or _json(self._document.get("invocation")) != self._body
                or _time(self._document["expires_at"]) <= datetime.now(timezone.utc)
            ):
                raise ValueError("permit is stale or changed; obtain a fresh grant")

    def _accepted_body(self, grant):
        current = decode_artifact(grant["document"])
        if (
            grant.get("permit_id") != self._permit_id
            or grant.get("authorization_granted") is not True
            or grant.get("automatic_retry_allowed") is not False
            or grant.get("status") != "dispatched"
            or grant.get("digest") != self._document_digest
            or _digest(current) != self._document_digest
            or _json(current.get("invocation")) != self._body
            or _time(current["expires_at"]) <= datetime.now(timezone.utc)
        ):
            raise ValueError("no current single-use grant for this invocation")
        return self._body

    def dispatch(self, send_invocation_bytes):
        self._begin()
        grant = self.workflow.dispatch_permit(
            self._permit_id, invocation_digest=self._document["invocation_digest"]
        )
        # Send the exact approved JSON bytes. A transport failure consumes this
        # attempt; callers reconcile the actual tool, never repeat it blindly.
        return send_invocation_bytes(self._accepted_body(grant))

    async def dispatch_async(self, send_invocation_bytes):
        """Async workflow and tool adapter; cancellation also consumes the attempt."""
        self._begin()
        grant = await self.workflow.dispatch_permit(
            self._permit_id, invocation_digest=self._document["invocation_digest"]
        )
        return await send_invocation_bytes(self._accepted_body(grant))
