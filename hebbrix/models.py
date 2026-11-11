"""Public response contracts for evidence-bearing Hebbrix operations."""

from typing import Any, Dict, List, TypedDict, Literal, Optional


class ActionAdviceReceipt(TypedDict, total=False):
    """Canonical advice envelope. ACT is never execution authorization."""

    gate: Literal["ASK", "REVIEW", "ACT", "BLOCK"]
    recommendation: str
    recommended_action: str
    action_confidence: Optional[float]
    blocked_by: Optional[str]
    blocked_hint: Optional[str]
    autonomy_evidence: Dict[str, Any]
    action_evidence: List[Dict[str, Any]]
    authorization_granted: bool
    execution_permission_required: bool


class GroundingReceipt(TypedDict, total=False):
    """Authoritative claim-grounding decision returned by the API."""

    status: str
    reason: str
    contract_version: str
    requested_predicate: str
    requested_attribute: str
    subject_anchors: List[str]


class EvidenceClaim(TypedDict, total=False):
    """Claims attributed to one exact memory evidence identifier."""

    memory_id: str
    claims: Dict[str, Any]


AnswerStatus = Literal[
    "answerable",
    "conflicting",
    "superseded",
    "unverified",
    "indexing",
    "no_relevant_memory",
]
RevisionStatus = Literal["current", "superseded", "conflicting", "historical"]


class MemoryRow(TypedDict, total=False):
    """One search row or Reason source, with its standing among the versions of
    what it states. Decide what to do with a response in code:
    ``hebbrix.should_answer``."""

    memory_id: str
    id: str
    content: str
    score: float
    rank: int
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str
    # True when the row is not evidence for the question: a retrieval candidate.
    low_confidence: bool
    is_current: bool
    revision_status: RevisionStatus
    superseded_by: Optional[str]
    supersedes: Optional[List[str]]
    conflicts_with: Optional[List[str]]
    valid_until: Optional[str]
    stated_at: Optional[str]
    replaced_values: Optional[List[str]]
    currency_basis: Optional[Literal["revision", "later_memory"]]


class ScopeIndexing(TypedDict, total=False):
    """Availability of accepted memories in the exact scope searched."""

    status: Literal["ready", "incomplete", "failed", "unknown"]
    pending_memories: int
    failed_memories: int
    capped: bool


class MemoryStatus(TypedDict, total=False):
    """Revision fields of ``GET /v1/memories/{id}`` (also on list and write
    responses, from the stored link alone)."""

    id: str
    searchable: bool
    searchability_reason: str
    conflict_status: str
    superseded_by_id: Optional[str]
    revision_status: RevisionStatus
    is_current: bool
    superseded_by: Optional[str]
    supersedes: Optional[List[str]]
    valid_until: Optional[str]
    stated_at: Optional[str]
    currency_basis: Optional[Literal["revision", "later_memory"]]
    replaced_values: Optional[List[str]]
    revision_link_status: Optional[Literal["pending", "completed", "failed"]]


class SearchSafetyEnvelope(TypedDict, total=False):
    """Fail-closed response shared by search and reasoning helpers."""

    query: str
    results: List[MemoryRow]
    sources: List[MemoryRow]
    total: int
    no_match: bool
    abstain_recommended: bool
    # What this response lets a caller do, in one value.
    answer_status: AnswerStatus
    indexing: Optional[ScopeIndexing]
    confidence_reason: Optional[str]
    # /v1/search/reason: decision_abstained is true exactly when answer is null.
    answer: Optional[str]
    decision_abstained: bool
    abstain_reason: Optional[str]
    cited_context: Optional[str]
    reasoning_status: Literal["completed", "partial", "timed_out"]
    timings: Dict[str, Any]
    query_confidence: float
    grounding: GroundingReceipt
    evidence_ids: List[str]
    evidence_claims: List[EvidenceClaim]
    safety_contract_version: str
    degraded: bool
    sdk_safety_reason: str
    proof_context: Dict[str, Any]
    # Entities the query names; each row carries applies_to/entity_match.
    query_entities: List[str]
    # Standing profile facts and preferences (search include_profile=True).
    profile: Dict[str, Any]
    # "compact" (SDK default) or absent for the full projection.
    view: str
