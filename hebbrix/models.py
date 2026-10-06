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


class SearchSafetyEnvelope(TypedDict, total=False):
    """Fail-closed response shared by search and reasoning helpers."""

    query: str
    results: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]
    total: int
    no_match: bool
    abstain_recommended: bool
    query_confidence: float
    grounding: GroundingReceipt
    evidence_ids: List[str]
    evidence_claims: List[EvidenceClaim]
    safety_contract_version: str
    degraded: bool
    sdk_safety_reason: str
    proof_context: Dict[str, Any]
