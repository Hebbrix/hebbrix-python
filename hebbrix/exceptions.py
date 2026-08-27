"""
Hebbrix SDK Exceptions
"""


class HebbrixError(Exception):
    """Base exception for Hebbrix SDK."""

    def __init__(
        self,
        message: str,
        status_code: int = None,
        *,
        code: str = None,
        request_id: str = None,
        details: dict = None,
    ):
        self.message = message
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        self.details = details or {}
        super().__init__(self.message)


class EntitlementError(HebbrixError):
    """The authenticated account lacks the plan or role for an operation."""

    def __init__(self, message: str, *, status_code: int, **kwargs):
        super().__init__(message, status_code=status_code, **kwargs)


class IndexingTimeoutError(TimeoutError):
    """A durable write did not become searchable before the client deadline.

    The write has already committed when this exception is raised.  Recovery
    metadata therefore lives on the exception so callers can resume polling or
    safely replay the *same* request with the same idempotency key instead of
    issuing an uncorrelated duplicate write.
    """

    def __init__(
        self,
        message: str,
        receipt: dict,
        *,
        idempotency_key: str = None,
    ):
        self.receipt = dict(receipt or {})

        candidates = [
            *(self.receipt.get("memory_ids") or []),
            self.receipt.get("memory_id"),
            self.receipt.get("id"),
            *(
                item.get("memory_id") or item.get("id")
                for item in (self.receipt.get("results") or [])
                if isinstance(item, dict)
            ),
        ]
        self.memory_ids = list(
            dict.fromkeys(str(value) for value in candidates if value)
        )
        self.job_id = self.receipt.get("job_id")
        self.status_url = self.receipt.get("status_url")
        if not self.status_url and self.memory_ids:
            self.status_url = f"/v1/memories/{self.memory_ids[0]}"
        if not self.status_url and self.job_id:
            self.status_url = f"/v1/memory-jobs/{self.job_id}"

        self.request_id = self.receipt.get("request_id")
        self.outbox_event_id = self.receipt.get("outbox_event_id")
        self.indexing_event_id = (
            self.receipt.get("indexing_event_id") or self.outbox_event_id
        )
        self.event_id = self.receipt.get("event_id") or self.indexing_event_id
        self.idempotency_key = idempotency_key or self.receipt.get("idempotency_key")
        self.idempotency_replay = self.receipt.get(
            "idempotency_replay",
            self.receipt.get("idempotency_replayed"),
        )
        self.retry_after = self.receipt.get("retry_after")
        self.recovery = {
            key: value
            for key, value in {
                "memory_ids": list(self.memory_ids),
                "job_id": self.job_id,
                "status_url": self.status_url,
                "request_id": self.request_id,
                "outbox_event_id": self.outbox_event_id,
                "indexing_event_id": self.indexing_event_id,
                "event_id": self.event_id,
                "idempotency_key": self.idempotency_key,
                "idempotency_replay": self.idempotency_replay,
                "retry_after": self.retry_after,
            }.items()
            if value not in (None, "", [])
        }
        super().__init__(message)


class AuthenticationError(HebbrixError):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed", **kwargs):
        super().__init__(message, status_code=401, **kwargs)


class ValidationError(HebbrixError):
    """Raised when request validation fails."""

    def __init__(self, message: str, errors: list = None, **kwargs):
        self.errors = errors or []
        super().__init__(message, status_code=422, **kwargs)


class NotFoundError(HebbrixError):
    """Raised when a resource is not found."""

    def __init__(self, message: str = "Resource not found", **kwargs):
        super().__init__(message, status_code=404, **kwargs)


class RateLimitError(HebbrixError):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", **kwargs):
        super().__init__(message, status_code=429, **kwargs)


class ServerError(HebbrixError):
    """Raised when server returns 5xx error."""

    def __init__(self, message: str = "Internal server error", **kwargs):
        super().__init__(message, status_code=500, **kwargs)
