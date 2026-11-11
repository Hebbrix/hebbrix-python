"""answer_context gives your own model the profile beside the rows it may use.

The chatbot guide asked search for include_profile=True and then built the
prompt from the rows alone, so a standing preference ("keep answers short")
that did not rank for the message never reached the model.
"""

from hebbrix import answer_context, should_answer


def row(memory_id, content, **fields):
    return {
        "memory_id": memory_id,
        "id": memory_id,
        "content": content,
        "score": 0.9,
        "low_confidence": False,
        "is_current": True,
        "revision_status": "current",
        **fields,
    }


def search(rows, profile=None, **fields):
    body = {
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
    if profile is not None:
        body["profile"] = profile
    return body


PROFILE = {
    "status": "ok",
    "facts": [
        {
            "category": "preference",
            "key": "answer_style",
            "value": "short answers",
            "confidence": 0.92,
            "updated_at": "2026-11-08T10:00:00Z",
        },
        {"category": "health", "key": "allergy", "value": "peanuts"},
    ],
    "count": 2,
    "avoid_topics": ["politics"],
    "end_user_id": "user-42",
    "as_of": "2026-11-08T10:00:00Z",
    "scope": {"collection_id": "c-1", "end_user_id": "user-42", "agent_id": None},
    "projection": {"status": "ready", "pending_writes": 0, "capped": False},
}

ALLERGY = row(
    "m1",
    "The user is allergic to peanuts.",
    stated_at="2026-11-02T09:00:00Z",
    subject="user",
    applies_to=[],
    metadata={"memory_type": "fact"},
    grounding={"status": "supported", "support_basis": "verified_span"},
)


def test_profile_and_rows_reach_the_model_with_their_dates_types_and_support():
    response = search([ALLERGY], PROFILE)
    assert answer_context(response) == (
        "Standing profile of this user (applies to every reply; collection_id c-1; "
        "end_user_id user-42; as of 2026-11-08; projection ready):\n"
        "- preference / answer_style: short answers (confidence 0.92, updated "
        "2026-11-08)\n"
        "- health / allergy: peanuts\n"
        "- avoid topics: politics\n"
        "\n"
        "Memories to answer from (current, supported for this message):\n"
        "[1] (fact; stated 2026-11-02; about user; current; support verified_span)\n"
        "The user is allergic to peanuts."
    )


def test_only_the_rows_should_answer_allows_are_listed():
    weak = row("m2", "Maybe the user likes cashews.", low_confidence=True)
    response = search([ALLERGY, weak], PROFILE)
    decision = should_answer(response)
    context = answer_context(response, decision)
    assert "cashews" not in context
    assert context.count("[1]") == 1 and "[2]" not in context


def test_a_declined_decision_keeps_the_standing_profile():
    response = search([ALLERGY], PROFILE, answer_status="no_relevant_memory")
    context = answer_context(response)
    assert context.startswith("Standing profile of this user")
    assert "Memories to answer from" not in context


def test_a_profile_still_being_projected_says_so():
    pending = {
        **PROFILE,
        "facts": [],
        "avoid_topics": [],
        "projection": {"status": "pending", "pending_writes": 50, "capped": True},
    }
    context = answer_context(search([], pending, answer_status="no_relevant_memory"))
    assert context == (
        "Standing profile of this user (applies to every reply; collection_id c-1; "
        "end_user_id user-42; as of 2026-11-08; projection pending):\n"
        "- still being updated: at least 50 recent writes not yet reflected; a fact "
        "here may be missing or about to change."
    )


def test_a_profile_whose_writes_failed_to_project_says_it_is_incomplete():
    failed = {
        **PROFILE,
        "facts": [],
        "avoid_topics": [],
        "projection": {
            "status": "failed",
            "pending_writes": 0,
            "failed_writes": 2,
            "capped": False,
            "failure": {"reason": "profile_extraction_failed", "retryable": True},
            "retry_after_seconds": None,
        },
    }
    context = answer_context(search([], failed, answer_status="no_relevant_memory"))
    assert context == (
        "Standing profile of this user (applies to every reply; collection_id c-1; "
        "end_user_id user-42; as of 2026-11-08; projection failed):\n"
        "- incomplete: 2 recent writes could not be reflected; a fact from them may "
        "be missing."
    )


def test_an_unavailable_profile_is_not_presented_as_empty():
    context = answer_context(
        search([ALLERGY], {"status": "unavailable", "facts": [], "count": 0})
    )
    assert context.startswith(
        "Standing profile of this user: unavailable for this request."
    )


def test_nothing_to_add_is_an_empty_string():
    assert answer_context(search([], answer_status="no_relevant_memory")) == ""
    assert answer_context(None) == ""


def test_history_rows_are_labelled_with_their_revision_status():
    old = row(
        "m0",
        "The user lived in Austin.",
        revision_status="superseded",
        is_current=False,
        stated_at="2025-01-05T00:00:00Z",
    )
    context = answer_context(search([old], answer_status="superseded"), history=True)
    assert context.splitlines()[:2] == [
        "Memories to answer from (earlier versions are labelled):",
        "[1] (stated 2025-01-05; superseded)",
    ]


def test_reason_sources_render_too():
    response = {
        "answer": "Peanuts.",
        "sources": [
            {
                "memory_id": "m1",
                "content": "The user is allergic to peanuts.",
                "revision_status": "current",
                "created_at": "2026-11-02T09:00:00Z",
                "metadata": {"memory_type": "fact"},
            }
        ],
        "answer_status": "answerable",
        "no_match": False,
        "abstain_recommended": False,
        "decision_abstained": False,
    }
    assert answer_context(response).splitlines() == [
        "Memories to answer from (current, supported for this message):",
        "[1] (fact; saved 2026-11-02; current)",
        "The user is allergic to peanuts.",
    ]


def test_a_suggestion_lists_its_context_as_neither_fact_nor_permission():
    from hebbrix import answer_context

    page = {
        "answer": None,
        "sources": [{"memory_id": "m1", "content": "The user owns a Fuji X-T5."}],
        "decision_abstained": True,
        "answer_status": "unverified",
        "grounding": {"status": "supported", "answerability": "context_only"},
    }
    text = answer_context(page)
    assert "The user owns a Fuji X-T5." in text
    assert "not established facts" in text and "never permission" in text
