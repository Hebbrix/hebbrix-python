"""The decision on a response is made in code, before a model sees anything."""

import json
import re
from pathlib import Path

import pytest
from hebbrix import AnswerDecision, should_answer, usable_memories
from hebbrix.answers import ACTIONS, ANSWER_STATUSES, REVISION_STATUSES
from hebbrix.resources import _canonical_search_envelope, _reason_payload, _search_payload

ROOT = Path(__file__).resolve().parents[3]
OPENAPI = ROOT / "docs/api/openapi.json"
# The public SDK repository carries no copy of the API's contract.
SCHEMAS = (
    json.loads(OPENAPI.read_text())["components"]["schemas"]
    if OPENAPI.exists()
    else {}
)
needs_contract = pytest.mark.skipif(not SCHEMAS, reason="no API contract here")


# The shapes /v1/search and /v1/search/reason return, with invented values.
def row(memory_id, **fields):
    return {
        "memory_id": memory_id,
        "id": memory_id,
        "content": f"memory {memory_id}",
        "score": 0.9,
        "low_confidence": False,
        "is_current": True,
        "revision_status": "current",
        "stated_at": "2026-11-07T00:00:00Z",
        **fields,
    }


def search(rows=None, **fields):
    rows = [row("new")] if rows is None else rows
    return {
        "query": "q",
        "results": rows,
        "total": len(rows),
        "no_match": False,
        "abstain_recommended": False,
        "answer_status": "answerable",
        "query_confidence": 0.9,
        "grounding": {"status": "supported"},
        "evidence_ids": [r["memory_id"] for r in rows],
        "safety_contract_version": "search-safety-v1",
        **fields,
    }


def source(memory_id, **fields):
    kept = row(memory_id)
    kept.pop("low_confidence")
    kept.update(fields)
    return kept


def reason(sources=None, **fields):
    sources = [source("new")] if sources is None else sources
    return {
        "answer": "Use green.",
        "sources": sources,
        "metadata": {},
        "no_match": False,
        "abstain_recommended": False,
        "decision_abstained": False,
        "abstain_reason": None,
        "cited_context": None,
        "answer_status": "answerable",
        "reasoning_status": "completed",
        "query_confidence": 0.9,
        "grounding": {"status": "supported"},
        "evidence_ids": [r["memory_id"] for r in sources],
        "safety_contract_version": "search-safety-v1",
        **fields,
    }


def ids(rows):
    return [r["memory_id"] for r in rows]


def test_an_answerable_search_gives_its_current_evidence_rows():
    decision = should_answer(search())
    assert isinstance(decision, AnswerDecision)
    assert decision  # usable as a condition
    assert decision.action == "answer"
    assert ids(decision.memories) == ["new"]
    assert usable_memories(search()) == decision.memories


def test_the_fields_a_model_needs_survive_the_decision():
    kept = should_answer(search()).memories[0]
    assert kept["revision_status"] == "current"
    assert kept["stated_at"] == "2026-11-07T00:00:00Z"


def test_only_established_current_rows_of_a_page_are_evidence():
    missing_confidence = row("unsaid")
    del missing_confidence["low_confidence"]
    missing_status = row("unlabelled")
    del missing_status["revision_status"]
    page = [
        row("new"),
        row("candidate", low_confidence=True),
        row("old", is_current=False, revision_status="superseded", low_confidence=True),
        row("copy", is_current=False, revision_status="historical"),
        missing_confidence,
        missing_status,
    ]
    decision = should_answer(search(page))
    assert ids(decision.memories) == ["new"]
    assert ids(decision.context) == [
        "candidate",
        "old",
        "copy",
        "unsaid",
        "unlabelled",
    ]


@pytest.mark.parametrize(
    "status, action",
    [(s, a) for s, a in ACTIONS.items() if s != "answerable"],
)
def test_every_other_status_never_reaches_a_model(status, action):
    rows = [] if status == "no_relevant_memory" else [row("m", low_confidence=True)]
    response = search(rows, answer_status=status)
    decision = should_answer(response)
    assert not decision
    assert decision.reason == status
    assert decision.action == action
    assert decision.memories == []
    assert usable_memories(response) == []


@pytest.mark.parametrize("flag", ["no_match", "abstain_recommended", "decision_abstained"])
def test_an_abstention_flag_overrides_an_answerable_status(flag):
    decision = should_answer(search(**{flag: True}))
    assert not decision
    assert decision.reason == flag
    assert decision.action == "abstain"
    assert decision.memories == []
    assert ids(decision.context) == ["new"]


def test_an_answerable_status_without_evidence_rows_abstains():
    decision = should_answer(search([row("m", low_confidence=True)]))
    assert not decision
    assert decision.reason == "no_usable_memories"


def test_reason_sources_carry_no_low_confidence_and_count_when_cited():
    decision = should_answer(reason())
    assert decision
    assert ids(decision.memories) == ["new"]


def test_a_flagged_reason_source_does_not_count():
    decision = should_answer(reason([source("new", low_confidence=True)]))
    assert not decision


def test_a_reason_abstention_gives_its_context_never_an_answer():
    decision = should_answer(
        reason(
            answer=None,
            decision_abstained=True,
            abstain_reason="decision_not_verified",
            answer_status="unverified",
            cited_context="Rule [1] does not cover this case.",
        )
    )
    assert not decision
    assert decision.action == "abstain"
    assert decision.cited_context == "Rule [1] does not cover this case."
    assert decision.memories == []


def test_a_reason_past_its_deadline_abstains_with_what_it_found():
    decision = should_answer(
        reason(
            answer=None,
            decision_abstained=True,
            abstain_reason="reasoning_timed_out",
            abstain_recommended=True,
            answer_status="unverified",
            reasoning_status="timed_out",
        )
    )
    assert not decision
    assert ids(decision.context) == ["new"]


def test_a_history_question_reads_earlier_versions_labelled():
    rows = [
        row("old", is_current=False, revision_status="superseded", low_confidence=True),
        row("copy", is_current=False, revision_status="historical", low_confidence=True),
        row("new"),
        row("candidate", low_confidence=True),
    ]
    page = search(rows, answer_status="superseded", abstain_recommended=True)
    assert not should_answer(page)
    decision = should_answer(page, history=True)
    assert decision
    assert decision.reason == "history"
    assert ids(decision.memories) == ["old", "copy", "new"]
    assert ids(decision.context) == ["candidate"]
    assert ids(usable_memories(page, history=True)) == ["old", "copy", "new"]


def test_a_conflict_is_never_resolved_by_asking_for_history():
    rows = [
        row("a", revision_status="conflicting", low_confidence=True),
        row("b", revision_status="conflicting", low_confidence=True),
    ]
    decision = should_answer(search(rows, answer_status="conflicting"), history=True)
    assert not decision
    assert decision.action == "ask_user"
    assert ids(decision.context) == ["a", "b"]


def test_a_history_question_with_nothing_earlier_follows_the_response():
    decision = should_answer(search([], answer_status="indexing"), history=True)
    assert decision.action == "retry"


@pytest.mark.parametrize("value", [None, "text", [], {}, {"results": [row("m")]}])
def test_a_response_it_does_not_understand_fails_closed(value):
    decision = should_answer(value)
    assert not decision
    assert decision.reason == "unsupported_response"
    assert decision.action == "abstain"


def test_an_unknown_status_fails_closed():
    decision = should_answer(search(answer_status="future_status"))
    assert not decision
    assert decision.reason == "malformed_response"
    assert decision.memories == []


def test_an_envelope_the_sdk_rejected_stays_rejected():
    broken = _canonical_search_envelope(search(safety_contract_version="future"))
    assert broken["sdk_safety_reason"]
    decision = should_answer(broken)
    assert not decision
    assert decision.reason == "malformed_response"


def test_a_degraded_response_the_sdk_preserved_is_decided_on_its_fields():
    degraded = _canonical_search_envelope(search(degraded=True))
    assert degraded["sdk_safety_reason"] == "degraded_evidence_preserved"
    assert should_answer(degraded)


def test_the_envelope_keeps_every_field_the_decision_reads():
    envelope = _canonical_search_envelope(
        reason(indexing={"status": "ready"}), rows_key="sources"
    )
    for field in (
        "answer_status",
        "decision_abstained",
        "abstain_reason",
        "cited_context",
        "reasoning_status",
        "indexing",
    ):
        assert field in envelope


def test_new_request_options_are_sent_only_when_set():
    assert "include_superseded" not in _search_payload("q")
    assert _search_payload("q", include_superseded=True)["include_superseded"] is True
    assert "deadline_ms" not in _reason_payload("q")
    assert _reason_payload("q", deadline_ms=2500)["deadline_ms"] == 2500


# ------------------------------------------------------------- API contract


@needs_contract
@pytest.mark.parametrize(
    "schema, fields",
    [
        (
            "SearchResult",
            [
                "low_confidence",
                "is_current",
                "revision_status",
                "superseded_by",
                "supersedes",
                "conflicts_with",
                "valid_until",
                "stated_at",
                "replaced_values",
                "currency_basis",
            ],
        ),
        (
            "SearchResponse",
            ["answer_status", "abstain_recommended", "no_match", "indexing"],
        ),
        (
            "ReasoningResponse",
            [
                "answer",
                "answer_status",
                "abstain_recommended",
                "decision_abstained",
                "abstain_reason",
                "cited_context",
                "reasoning_status",
                "indexing",
                "timings",
            ],
        ),
        (
            "MemoryWithMetadata",
            [
                "revision_status",
                "is_current",
                "superseded_by",
                "superseded_by_id",
                "supersedes",
                "valid_until",
                "stated_at",
                "currency_basis",
                "replaced_values",
                "revision_link_status",
            ],
        ),
    ],
)
def test_the_typed_fields_are_what_the_api_returns(schema, fields):
    properties = SCHEMAS[schema]["properties"]
    assert [field for field in fields if field not in properties] == []


@needs_contract
def test_the_statuses_are_the_apis():
    text = SCHEMAS["SearchResponse"]["properties"]["answer_status"]["description"]
    assert all(status in text for status in ANSWER_STATUSES)
    assert set(ACTIONS) == set(ANSWER_STATUSES)
    for schema in ("MemoryWithMetadata", "MemoryResponse"):
        text = SCHEMAS[schema]["properties"]["revision_status"]["description"]
        assert all(status in text for status in REVISION_STATUSES)


@needs_contract
def test_the_typescript_helper_decides_the_same():
    source_text = (ROOT / "sdk/typescript/src/answers.ts").read_text()
    for status, action in ACTIONS.items():
        assert re.search(rf'\b{status}: "{action}"', source_text), status
    for status in REVISION_STATUSES:
        assert f'"{status}"' in source_text
    assert "degraded_evidence_preserved" in source_text


def test_an_unverified_permission_is_its_own_action_with_the_rule_as_context():
    # The rule restricting the act to a group is evidence of the rule; whether
    # the asker belongs to the group is not established, so nothing is answered.
    response = search(
        [row("rule")],
        answer_status="unverified",
        abstain_recommended=True,
        confidence_reason="authorization_not_verifiable",
    )
    decision = should_answer(response)
    assert not decision
    assert decision.reason == "authorization_not_verifiable"
    assert decision.action == "verify_authorization"
    assert decision.memories == []
    assert ids(decision.context) == ["rule"]


@needs_contract
def test_the_authorization_reason_is_the_apis():
    text = SCHEMAS["SearchResponse"]["properties"]["confidence_reason"]["description"]
    assert "authorization_not_verifiable" in text


def test_history_never_overrides_an_unverified_response():
    # The server could not establish any row: earlier versions among them are
    # not evidence for the past either.
    rows = [row("old", is_current=False, revision_status="historical", low_confidence=True)]
    page = search(rows, answer_status="unverified", abstain_recommended=True)
    decision = should_answer(page, history=True)
    assert not decision
    assert decision.action == "abstain"
    assert ids(decision.context) == ["old"]


def test_a_high_stakes_answer_waits_for_a_ready_index():
    ready = {"status": "ready", "answer_risk": "none"}
    assert should_answer(search(indexing=ready), require_ready=True)
    for indexing in (
        {"status": "incomplete", "answer_risk": "may_change"},
        {"status": "ready", "answer_risk": "may_change"},
        None,
    ):
        decision = should_answer(search(indexing=indexing), require_ready=True)
        assert not decision
        assert decision.action == "retry"
        assert decision.reason == "index_not_ready"
    # Without it, a response the server lets answer while indexing answers.
    assert should_answer(search(indexing={"status": "incomplete", "answer_risk": "may_change"}))


def test_a_suggestion_is_context_to_shape_never_an_answer():
    page = reason(
        [source("camera")],
        answer=None,
        decision_abstained=True,
        grounding={"status": "supported", "answerability": "context_only"},
    )
    decision = should_answer(page)
    assert not decision
    assert decision.action == "use_as_context"
    assert decision.memories == []
    assert ids(decision.context) == ["camera"]


@pytest.mark.parametrize("flag", ["abstain_recommended", "decision_abstained", "no_match"])
def test_an_answerable_status_beside_an_abstention_flag_fails_closed_in_every_mode(flag):
    # A contradictory envelope (the server never sends one): answerable, an
    # explicit abstention flag, and only an earlier, unestablished row.
    page = search(
        [
            row(
                "synthetic-history",
                revision_status="historical",
                is_current=False,
                low_confidence=True,
            )
        ],
        indexing={"status": "ready", "answer_risk": "none"},
        **{flag: True},
    )
    for options in ({}, {"history": True}, {"history": True, "require_ready": True}):
        decision = should_answer(page, **options)
        assert not decision
        assert decision.reason == flag
        assert decision.action == "abstain"
        assert decision.memories == []
        assert usable_memories(page, **options) == []


def test_a_superseded_reason_result_still_answers_a_history_question():
    # Reason marks a result superseded only when it abstains for the present
    # (decision_abstained), so that flag is what a question about the past reads.
    page = reason(
        [source("old", is_current=False, revision_status="superseded")],
        answer=None,
        decision_abstained=True,
        answer_status="superseded",
    )
    assert not should_answer(page)
    decision = should_answer(page, history=True)
    assert decision
    assert decision.reason == "history"
    assert ids(decision.memories) == ["old"]


def test_history_never_answers_a_response_that_matched_nothing():
    page = search(
        [row("old", is_current=False, revision_status="superseded", low_confidence=True)],
        answer_status="superseded",
        abstain_recommended=True,
        no_match=True,
    )
    decision = should_answer(page, history=True)
    assert not decision
    assert decision.reason == "superseded"


def test_an_applicable_rule_is_policy_context_never_an_answer():
    rows = [
        row("case", low_confidence=True, evidence_role="related"),
        row("rule", low_confidence=True, evidence_role="applicable_rule"),
    ]
    page = search(
        rows,
        answer_status="unverified",
        abstain_recommended=True,
        confidence_reason="soft_claim_candidate",
    )
    decision = should_answer(page)
    assert not decision
    assert decision.reason == "applicable_rule"
    assert decision.action == "use_as_context"
    assert decision.memories == []
    assert ids(decision.context) == ["rule", "case"]
    assert usable_memories(page) == []


def test_a_rule_never_answers_an_authorization_question():
    rows = [row("rule", low_confidence=True, evidence_role="applicable_rule")]
    page = search(
        rows,
        answer_status="unverified",
        abstain_recommended=True,
        confidence_reason="authorization_not_verifiable",
    )
    decision = should_answer(page)
    assert not decision
    assert decision.reason == "authorization_not_verifiable"
