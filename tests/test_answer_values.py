"""Search rows' values and value conflicts reach your model as what they are.

SDK 2.11.0 rendered ``applies_to`` as "names ...", so a rule's required code
read as a name ("names EXP-7"), and it never showed ``values`` (server 1.4.45)
or ``value_conflicts`` (server 1.4.46). ``applies_to`` is what a memory is
about; ``values`` is what it requires or gives; a value conflict means the task
names a different value of the same kind than one the memory requires.
"""

from unittest.mock import AsyncMock, Mock

import pytest

import hebbrix
from hebbrix import MemoryRow, ValueConflict, answer_context, should_answer
from hebbrix.resources import SearchResource
from hebbrix.sync_client import SyncSearchResource

HEADING = "Memories to answer from (current, supported for this message):"


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


def search(rows, **fields):
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


def rule(**fields):
    return row(
        "r1",
        "Orders for Acme need customs form EXP-7.",
        stated_at="2026-11-02T09:00:00Z",
        metadata={"memory_type": "rule"},
        grounding={"status": "supported", "support_basis": "verified_span"},
        **fields,
    )


def lines(rows, **fields):
    return answer_context(search(rows, **fields)).splitlines()


# Presence: the fields reach the caller untouched.


@pytest.mark.asyncio
async def test_both_clients_keep_values_and_conflicts_on_each_row():
    conflict = {"value": "EXP-7", "query_value": "EXP-9", "kind": "customs_form"}
    envelope = search(
        [
            rule(
                applies_to=["Acme"],
                entity_match="match",
                values=["EXP-7"],
                value_conflicts=[conflict],
            )
        ]
    )
    sync, asynchronous = Mock(), Mock()
    sync.post.return_value = dict(envelope)
    asynchronous.post = AsyncMock(return_value=dict(envelope))
    first = SyncSearchResource(sync).search_with_proof("q", user_id="u")
    second = await SearchResource(asynchronous).search_with_proof("q", user_id="u")
    for response in (first, second):
        (kept,) = response["results"]
        assert kept["applies_to"] == ["Acme"] and kept["entity_match"] == "match"
        assert kept["values"] == ["EXP-7"]
        # An unknown key on a conflict is kept, not stripped.
        assert kept["value_conflicts"] == [conflict]
        assert "sdk_safety_reason" not in response


def test_row_types_name_the_entity_and_value_fields_and_require_none():
    fields = MemoryRow.__annotations__
    for name in ("applies_to", "entity_match", "values", "value_conflicts"):
        assert name in fields
    assert MemoryRow.__total__ is False
    assert set(ValueConflict.__annotations__) == {"value", "query_value"}
    assert ValueConflict.__total__ is False
    assert "ValueConflict" in hebbrix.__all__


# Rendering.


def test_applies_to_reads_as_what_the_memory_is_about():
    text = lines([rule(applies_to=["Acme", "order 5531"])])
    assert text == [
        HEADING,
        "[1] (rule; stated 2026-11-02; about: Acme, order 5531; current; "
        "support verified_span)",
        "Orders for Acme need customs form EXP-7.",
    ]
    assert not any("names" in line for line in text)


def test_a_required_code_reads_as_a_value_not_a_name():
    text = lines([rule(applies_to=["Acme"], values=["EXP-7"])])
    assert text == [
        HEADING,
        "[1] (rule; stated 2026-11-02; about: Acme; requires or gives: EXP-7; "
        "current; support verified_span)",
        "Orders for Acme need customs form EXP-7.",
    ]


def test_a_code_listed_in_applies_to_and_values_reads_once_as_a_value():
    text = lines([rule(applies_to=["Acme", "exp-7"], values=["EXP-7", "MGR-2"])])
    assert text[1] == (
        "[1] (rule; stated 2026-11-02; about: Acme; requires or gives: EXP-7, "
        "MGR-2; current; support verified_span)"
    )


def test_values_without_applies_to_still_render():
    text = lines([rule(values=["EXP-7"])])
    assert text[1] == (
        "[1] (rule; stated 2026-11-02; requires or gives: EXP-7; current; "
        "support verified_span)"
    )


def test_a_value_conflict_is_stated_before_the_memory_text():
    conflicted = rule(
        applies_to=["Acme"],
        values=["EXP-7"],
        value_conflicts=[{"value": "EXP-7", "query_value": "EXP-9"}],
    )
    assert lines([conflicted]) == [
        HEADING,
        "[1] (rule; stated 2026-11-02; about: Acme; requires or gives: EXP-7; "
        "current; support verified_span)",
        "Conflicts with the task: task says EXP-9, memory requires EXP-7.",
        "Orders for Acme need customs form EXP-7.",
    ]


def test_each_conflict_gets_one_line_and_repeats_collapse():
    conflicted = rule(
        values=["EXP-7", "MGR-2"],
        value_conflicts=[
            {"value": "EXP-7", "query_value": "EXP-9"},
            {"value": "MGR-2", "query_value": "MGR-5"},
            {"value": "EXP-7", "query_value": "EXP-9"},
        ],
    )
    text = lines([conflicted])
    assert text[2:] == [
        "Conflicts with the task: task says EXP-9, memory requires EXP-7.",
        "Conflicts with the task: task says MGR-5, memory requires MGR-2.",
        "Orders for Acme need customs form EXP-7.",
    ]


def test_conflicts_are_listed_under_their_own_memory():
    plain = row("m2", "Acme ships from Rotterdam.", applies_to=["Acme"])
    conflicted = rule(value_conflicts=[{"value": "EXP-7", "query_value": "EXP-9"}])
    text = lines([plain, conflicted])
    assert text == [
        HEADING,
        "[1] (about: Acme; current)",
        "Acme ships from Rotterdam.",
        "[2] (rule; stated 2026-11-02; current; support verified_span)",
        "Conflicts with the task: task says EXP-9, memory requires EXP-7.",
        "Orders for Acme need customs form EXP-7.",
    ]


def test_a_conflict_missing_one_side_still_warns():
    text = lines(
        [
            rule(
                value_conflicts=[
                    {"value": "EXP-7"},
                    {"query_value": "EXP-9", "value": None},
                    {"value": 7, "query_value": 9},
                ]
            )
        ]
    )
    assert text[2:5] == [
        "Conflicts with the task: task says a different value, memory requires "
        "EXP-7.",
        "Conflicts with the task: task says EXP-9, memory requires a different "
        "value.",
        "Conflicts with the task: task says 9, memory requires 7.",
    ]


def test_a_suggestion_renders_values_and_conflicts_as_context():
    page = {
        "answer": None,
        "sources": [
            {
                "memory_id": "r1",
                "content": "Orders for Acme need customs form EXP-7.",
                "applies_to": ["Acme"],
                "values": ["EXP-7"],
                "value_conflicts": [{"value": "EXP-7", "query_value": "EXP-9"}],
            }
        ],
        "decision_abstained": True,
        "answer_status": "unverified",
        "grounding": {"status": "supported", "answerability": "context_only"},
    }
    assert answer_context(page).splitlines()[1:] == [
        "[1] (about: Acme; requires or gives: EXP-7)",
        "Conflicts with the task: task says EXP-9, memory requires EXP-7.",
        "Orders for Acme need customs form EXP-7.",
    ]


# Absence and malformed input: older servers and unknown shapes.


def test_rows_without_the_new_fields_render_as_before():
    old = rule(applies_to=[])
    assert lines([old]) == [
        HEADING,
        "[1] (rule; stated 2026-11-02; current; support verified_span)",
        "Orders for Acme need customs form EXP-7.",
    ]
    assert lines([old]) == lines([rule()])


@pytest.mark.parametrize(
    "fields",
    [
        {"values": None, "value_conflicts": None, "applies_to": None},
        {"values": "EXP-7", "value_conflicts": {"value": "EXP-7"}},
        {"values": [None, "", 7, {"v": 1}], "applies_to": [None, "", 3]},
        {"value_conflicts": [None, "EXP-7", [], {}, {"unknown": "EXP-9"}]},
        {"value_conflicts": [{"value": " ", "query_value": True}]},
    ],
)
def test_malformed_fields_add_nothing(fields):
    assert lines([rule(**fields)]) == lines([rule()])


def test_values_and_conflicts_do_not_change_the_decision():
    plain = search([rule(applies_to=["Acme"])])
    annotated = search(
        [
            rule(
                applies_to=["Acme"],
                values=["EXP-7"],
                value_conflicts=[{"value": "EXP-7", "query_value": "EXP-9"}],
            )
        ]
    )
    before, after = should_answer(plain), should_answer(annotated)
    assert (before.answer, before.reason, before.action) == (
        after.answer,
        after.reason,
        after.action,
    )
    assert [r["memory_id"] for r in after.memories] == ["r1"]
