import pytest
from hebbrix.resources import _canonical_search_envelope


@pytest.mark.parametrize(
    "patch",
    [
        {"sources": [{"content": "unidentified"}]},
        {"sources": [None]},
        {"sources": ["not a row"]},
        {"sources": [{"memory_id": 7}]},
        {"sources": [{"memory_id": " "}]},
        {"sources": [{"memory_id": None, "id": "m-1"}]},
        {"sources": [{"memory_id": "m-1", "id": "m-2"}]},
        {"sources": {}},
        {"sources": []},
        {"evidence_ids": [7]},
        {"evidence_ids": [None]},
        {"evidence_ids": ["m-1", "m-1"]},
        {"safety_contract_version": None},
        {"safety_contract_version": "future-version"},
        {"no_match": True},
    ],
)
def test_malformed_evidence_never_exposes_unsupported_synthesis(patch):
    response = {
        "sources": [{"memory_id": "m-1", "content": "fact"}],
        "answer": "unsupported answer",
        "citations": ["m-1"],
        "no_match": False,
        "abstain_recommended": False,
        "query_confidence": 0.9,
        "grounding": {"status": "supported"},
        "evidence_ids": ["m-1"],
        "safety_contract_version": "search-safety-v1",
    }
    result = _canonical_search_envelope(dict(response, **patch), rows_key="sources")
    assert result["sources"] == [] and result["evidence_ids"] == []
    assert result["answer"] is None and result["citations"] == []
    assert result["no_match"] is True and result["abstain_recommended"] is True
    assert result["query_confidence"] == 0
    assert response["sources"]  # Caller-owned envelope was not mutated.
