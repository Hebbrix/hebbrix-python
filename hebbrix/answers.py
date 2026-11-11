"""Decide in code what a search or Reason response lets you do.

A model that is told "abstain_recommended: true" can still answer. Call
``should_answer`` before invoking the model and give it only
``decision.memories``: when the decision is not to answer, the model is never
called, so it cannot ignore the flag.

    response = await client.search_with_proof(
        question, user_id=user_id, include_profile=True
    )
    decision = should_answer(response)
    if not decision:
        return reply_for(decision.action)  # your own fixed reply per action
    return await my_llm(question, context=answer_context(response, decision))

``answer_context`` renders the end user's standing profile beside those rows,
so a preference that did not rank for this message still reaches the model.

``search()`` returns only the rows, without the fields this needs; use
``search_with_proof()`` or ``reason()``. The decision is derived from the
response alone: nothing here calls the API, and it fails closed on a response it
does not understand.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

ANSWER_STATUSES = (
    "answerable",
    "conflicting",
    "superseded",
    "unverified",
    "indexing",
    "no_relevant_memory",
)
REVISION_STATUSES = ("current", "superseded", "conflicting", "historical")

# What to do instead of answering, for each ``answer_status``.
ACTIONS = {
    "answerable": "answer",
    "conflicting": "ask_user",
    "superseded": "say_no_longer_current",
    "unverified": "abstain",
    "indexing": "retry",
    "no_relevant_memory": "say_unknown",
}
# A permission question answered by a rule that restricts the act to a group no
# memory ties the asker to (``confidence_reason`` "authorization_not_verifiable"):
# the rule is in ``context``; check the asker's role in your own system.
AUTHORIZATION_NOT_VERIFIABLE = "authorization_not_verifiable"
VERIFY_AUTHORIZATION = "verify_authorization"
# A Reason request for a suggestion or plan ("Can you suggest accessories for my
# camera?") has no stored answer: its sources are the memories that should shape
# what your model composes (``grounding.answerability`` "context_only"). They are
# context, never a verified fact or a permission.
CONTEXT_ONLY = "context_only"
USE_AS_CONTEXT = "use_as_context"
# ``require_ready``: the scope's index is not complete, or the server says the
# answer may still change (``indexing.answer_risk``).
INDEX_NOT_READY = "index_not_ready"
# Set by the SDK on a response whose rows it kept although it is degraded: not a
# malformed envelope, so it is not a reason to fail closed on its own.
_PRESERVED = "degraded_evidence_preserved"
_PAST = frozenset({"superseded", "historical"})


@dataclass(frozen=True)
class AnswerDecision:
    """What a response lets you do; true only when you may answer from it."""

    answer: bool
    reason: str
    action: str
    # Safe to pass to a model as evidence; empty unless ``answer`` is true.
    memories: List[Dict[str, Any]] = field(default_factory=list)
    # The other rows returned, each with its revision_status and low_confidence:
    # to show or to ask about ("which of these holds?"), never to answer from.
    context: List[Dict[str, Any]] = field(default_factory=list)
    # Reason only: context for a decision it could not verify, with citations.
    cited_context: Optional[str] = None

    def __bool__(self) -> bool:
        return self.answer


def _rows(response: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], bool]:
    """The response's rows, and whether they are search rows (which always say
    ``low_confidence``) rather than Reason's cited sources."""

    results = response.get("results")
    if isinstance(results, list):
        return [row for row in results if isinstance(row, dict)], True
    sources = response.get("sources")
    if isinstance(sources, list):
        return [row for row in sources if isinstance(row, dict)], False
    return [], False


def _is_evidence(row: Mapping[str, Any], *, search_row: bool) -> bool:
    """A current row established as evidence. A row that does not say so is not."""

    if row.get("revision_status") != "current" or row.get("is_current") is False:
        return False
    confidence = row.get("low_confidence")
    return confidence is False if search_row else confidence is not True


def _is_history(row: Mapping[str, Any], *, search_row: bool) -> bool:
    """A row a question about the past may read: an earlier version, labelled as
    one (the server flags those low_confidence for the present), or evidence."""

    return row.get("revision_status") in _PAST or _is_evidence(
        row, search_row=search_row
    )


def _ready(response: Mapping[str, Any]) -> bool:
    """Whether the response says its scope is fully indexed with nothing that
    could change the answer. A response that does not say is not ready."""

    indexing = response.get("indexing")
    if not isinstance(indexing, Mapping):
        return False
    return indexing.get("status") == "ready" and indexing.get("answer_risk") in (
        None,
        "none",
    )


def should_answer(
    response: Optional[Mapping[str, Any]],
    *,
    history: bool = False,
    require_ready: bool = False,
) -> AnswerDecision:
    """Whether you may answer from ``response`` (a ``search_with_proof`` or
    ``reason`` result), the rows to answer from, and what to do when you may not.

    Every server signal is enforced: ``answer_status``, ``no_match``,
    ``abstain_recommended``, ``decision_abstained``, ``confidence_reason`` and
    each row's ``low_confidence`` and ``revision_status``.

    ``require_ready=True`` is for high-stakes flows (money, health, actions):
    the answer is also held, with action ``retry``, until ``indexing.status`` is
    ``ready`` and ``indexing.answer_risk`` is ``none``. Without it an answer
    from a scope still indexing is allowed when the server allows it
    (``answer_risk`` ``may_change``), and a count, total or list is always held
    while indexing (``answer_status`` ``indexing``).

    ``history=True`` is for a question about the past that your application
    recognises ("Where did I live before?"). It overrides one thing: a
    superseded or historical row then counts as evidence, so a response the
    server answered or marked ``superseded`` can be answered from its earlier
    versions. It never overrides ``unverified``, ``no_relevant_memory``,
    ``indexing``, ``conflicting`` or ``authorization_not_verifiable``. Keep each
    row's ``revision_status`` and ``stated_at`` in what you pass to the model, so
    it can tell the versions apart.

    A Reason result for a suggestion or plan (``context_only``) returns action
    ``use_as_context``: give ``decision.context`` to your model to shape what it
    suggests, never as an established fact or a permission to act.
    """

    if not isinstance(response, Mapping) or "answer_status" not in response:
        return AnswerDecision(False, "unsupported_response", "abstain")
    status = response.get("answer_status")
    safety = response.get("sdk_safety_reason")
    if status not in ANSWER_STATUSES or (safety and safety != _PRESERVED):
        return AnswerDecision(False, "malformed_response", "abstain")
    rows, search_rows = _rows(response)
    cited = response.get("cited_context")
    cited = cited if isinstance(cited, str) and cited else None

    def declined(reason: str, action: str) -> AnswerDecision:
        return AnswerDecision(False, reason, action, [], rows, cited)

    if status == "conflicting":
        return declined(status, ACTIONS[status])
    if response.get("confidence_reason") == AUTHORIZATION_NOT_VERIFIABLE:
        return declined(AUTHORIZATION_NOT_VERIFIABLE, VERIFY_AUTHORIZATION)
    grounding = response.get("grounding")
    if isinstance(grounding, Mapping) and grounding.get("answerability") == CONTEXT_ONLY:
        return declined(CONTEXT_ONLY, USE_AS_CONTEXT)
    if require_ready and not _ready(response):
        return declined(INDEX_NOT_READY, "retry")
    if history and status in ("answerable", "superseded"):
        usable = [row for row in rows if _is_history(row, search_row=search_rows)]
        if usable:
            others = [row for row in rows if row not in usable]
            return AnswerDecision(True, "history", "answer", usable, others, cited)
    if status != "answerable":
        return declined(status, ACTIONS[status])
    for flag in ("no_match", "abstain_recommended", "decision_abstained"):
        if response.get(flag) is True:
            return declined(flag, "abstain")
    usable = [row for row in rows if _is_evidence(row, search_row=search_rows)]
    if not usable:
        return declined("no_usable_memories", "abstain")
    others = [row for row in rows if row not in usable]
    return AnswerDecision(True, status, "answer", usable, others, cited)


def usable_memories(
    response: Optional[Mapping[str, Any]],
    *,
    history: bool = False,
    require_ready: bool = False,
) -> List[Dict[str, Any]]:
    """The rows of ``response`` safe to pass to a model as evidence; empty when
    ``should_answer`` says not to answer."""

    return should_answer(
        response, history=history, require_ready=require_ready
    ).memories


def _day(value: Any) -> Optional[str]:
    """The calendar date of an ISO timestamp (the API's dates are ISO 8601)."""

    return str(value)[:10] if isinstance(value, str) and value else None


def _count(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _profile_lines(profile: Any) -> List[str]:
    if not isinstance(profile, Mapping):
        return []
    if profile.get("status") != "ok":
        # Unreadable is not empty: a preference may exist that was not returned.
        return ["Standing profile of this user: unavailable for this request."]
    facts = [
        fact
        for fact in profile.get("facts") or []
        if isinstance(fact, Mapping) and fact.get("value") not in (None, "")
    ]
    avoid = [t for t in profile.get("avoid_topics") or [] if isinstance(t, str) and t]
    projection = profile.get("projection")
    projection = projection if isinstance(projection, Mapping) else {}
    pending = projection.get("status") == "pending"
    failed = projection.get("status") == "failed"
    if not facts and not avoid and not pending and not failed:
        return []
    scope = profile.get("scope")
    scope = (
        scope
        if isinstance(scope, Mapping)
        else {"end_user_id": profile.get("end_user_id")}
    )
    details = [f"{key} {value}" for key, value in scope.items() if value]
    if _day(profile.get("as_of")):
        details.append(f"as of {_day(profile.get('as_of'))}")
    if projection.get("status"):
        details.append(f"projection {projection['status']}")
    header = "Standing profile of this user (applies to every reply"
    lines = [header + ("; " + "; ".join(details) if details else "") + "):"]
    for fact in facts:
        name = " / ".join(str(fact[k]) for k in ("category", "key") if fact.get(k))
        meta = []
        if isinstance(fact.get("confidence"), (int, float)):
            meta.append(f"confidence {float(fact['confidence']):.2f}")
        if _day(fact.get("updated_at")):
            meta.append(f"updated {_day(fact.get('updated_at'))}")
        text = f"{name}: {fact['value']}" if name else str(fact["value"])
        lines.append(f"- {text}" + (f" ({', '.join(meta)})" if meta else ""))
    if avoid:
        lines.append("- avoid topics: " + ", ".join(avoid))
    if pending:
        count = projection.get("pending_writes")
        writes = (
            f"{'at least ' if projection.get('capped') else ''}{count} recent writes"
            if isinstance(count, int) and count > 0
            else "recent writes"
        )
        lines.append(
            f"- still being updated: {writes} not yet reflected; a fact here may be "
            "missing or about to change."
        )
    elif failed:
        count = projection.get("failed_writes")
        writes = (
            f"{count} recent writes"
            if isinstance(count, int) and count > 0
            else "recent writes"
        )
        lines.append(
            f"- incomplete: {writes} could not be reflected; a fact from them may be "
            "missing."
        )
    return lines


def _memory_details(row: Mapping[str, Any]) -> List[str]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    details = []
    memory_type = metadata.get("memory_type") or row.get("memory_type")
    if memory_type:
        details.append(str(memory_type))
    if _day(row.get("stated_at")):
        details.append(f"stated {_day(row.get('stated_at'))}")
    elif _day(row.get("created_at")):
        details.append(f"saved {_day(row.get('created_at'))}")
    if _day(row.get("valid_until")):
        details.append(f"valid until {_day(row.get('valid_until'))}")
    if row.get("subject"):
        details.append(f"about {row['subject']}")
    applies_to = row.get("applies_to")
    names = (
        [n for n in applies_to if isinstance(n, str) and n]
        if isinstance(applies_to, list)
        else []
    )
    if names:
        details.append("names " + ", ".join(names))
    if row.get("revision_status"):
        details.append(str(row["revision_status"]))
    grounding = row.get("grounding")
    if not isinstance(grounding, Mapping):
        grounding = metadata.get("grounding")
    if isinstance(grounding, Mapping):
        support = grounding.get("support_basis") or grounding.get("status")
        if support:
            details.append(f"support {support}")
    outcomes = metadata.get("outcome_evidence")
    if isinstance(outcomes, Mapping) and (
        outcomes.get("successes") or outcomes.get("failures")
    ):
        details.append(
            f"outcomes {_count(outcomes.get('successes'))} worked, "
            f"{_count(outcomes.get('failures'))} failed"
        )
    return details


def answer_context(
    response: Optional[Mapping[str, Any]],
    decision: Optional[AnswerDecision] = None,
    *,
    history: bool = False,
    require_ready: bool = False,
) -> str:
    """The text to give your own model with the user's message: the end user's
    standing profile and the memories ``should_answer`` lets you answer from.

    Pass a ``search_with_proof(..., include_profile=True)`` or ``reason()``
    response, and the decision you already made on it (computed here when
    omitted). The profile section lists each standing fact with its category,
    confidence and date, the topics to avoid, the profile's scope, and whether
    it is still being projected from recent writes; an unavailable profile is
    said to be unavailable, never left out as if empty. The memories section
    lists only ``decision.memories``, numbered for citation, each with its
    memory type, date, whom it is about, the names it states, its revision
    status and its support. When the decision is not to answer, only the
    profile is returned: standing preferences still shape a reply such as
    "I don't know that yet". For a Reason suggestion or plan (``context_only``)
    the memories that should shape it are listed as context, marked as neither
    established facts nor permission to act. Returns "" when there is nothing to
    add.
    """

    if decision is None:
        decision = should_answer(
            response, history=history, require_ready=require_ready
        )
    sections = []
    profile = _profile_lines(
        response.get("profile") if isinstance(response, Mapping) else None
    )
    if profile:
        sections.append("\n".join(profile))
    if decision.answer and decision.memories:
        heading = (
            "Memories to answer from (earlier versions are labelled):"
            if decision.reason == "history"
            else "Memories to answer from (current, supported for this message):"
        )
        lines = [heading]
        for index, row in enumerate(decision.memories, start=1):
            details = _memory_details(row)
            lines.append(f"[{index}]" + (f" ({'; '.join(details)})" if details else ""))
            lines.append(str(row.get("content") or ""))
        sections.append("\n".join(lines))
    elif decision.reason == CONTEXT_ONLY and decision.context:
        lines = [
            "Memories that should shape the suggestion (context: not established "
            "facts, and never permission to act):"
        ]
        for index, row in enumerate(decision.context, start=1):
            details = _memory_details(row)
            lines.append(f"[{index}]" + (f" ({'; '.join(details)})" if details else ""))
            lines.append(str(row.get("content") or ""))
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
