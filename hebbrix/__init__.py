"""Typed async-first client for Hebbrix memory and outcome-learning APIs.

The public surface and its plan/role restrictions are documented by the
production OpenAPI and ``GET /v1/users/me/capabilities``. The experimental
World Model is intentionally absent from this release.
"""

__version__ = "2.11.0"
__author__ = "Hebbrix Team"
__license__ = "MIT"

from hebbrix.answers import (
    AnswerDecision,
    answer_context,
    should_answer,
    usable_memories,
)
from hebbrix.chat import MemoryChat
from hebbrix.client import MemoryClient
from hebbrix.exceptions import (
    AuthenticationError,
    EntitlementError,
    HebbrixError,
    IndexingTimeoutError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from hebbrix.models import (
    ActionAdviceReceipt,
    AnswerFinality,
    AnswerStatus,
    EvidenceClaim,
    GroundingReceipt,
    MemoryRow,
    MemoryStatus,
    RevisionStatus,
    ScopeIndexing,
    SearchSafetyEnvelope,
)
from hebbrix.sync_client import SyncMemoryClient

__all__ = [
    "MemoryClient",
    "SyncMemoryClient",
    "MemoryChat",
    "HebbrixError",
    "AuthenticationError",
    "EntitlementError",
    "IndexingTimeoutError",
    "ValidationError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
    "GroundingReceipt",
    "EvidenceClaim",
    "SearchSafetyEnvelope",
    "ActionAdviceReceipt",
    "AnswerDecision",
    "AnswerFinality",
    "AnswerStatus",
    "MemoryRow",
    "MemoryStatus",
    "RevisionStatus",
    "ScopeIndexing",
    "answer_context",
    "should_answer",
    "usable_memories",
]
