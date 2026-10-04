import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from hebbrix.experience import ExperienceRequest, _digest


def fixture():
    scope = {
        "memory_collection_id": "lessons",
        "evidence_collection_id": "facts",
        "user_id": "customer",
        "agent_id": None,
        "run_id": None,
        "policy_key": "v1",
    }
    target = {"stateful": True, "service": "unseen"}
    context = {
        "schema_version": "experience-context-v1",
        "scope": scope,
        "target_context_digest": _digest(target),
        "authorization_granted": False,
        "lessons": [
            {
                "memory_id": "lesson",
                "record_digest": "b" * 64,
                "trust": "untrusted_experience_hypothesis",
                "lesson": "Evaluate the boundary.",
                "authorization_granted": False,
                "lesson_truth_verified": False,
            }
        ],
    }
    response = {
        "context": context,
        "context_digest": _digest(context),
        "no_match": False,
        "assessed_at": datetime.now(timezone.utc).isoformat(),
        "authorization_granted": False,
        "actor_exposure_verified": False,
        "revalidation_required": True,
    }
    return {
        "response": response,
        "request": {
            "model": "model-version",
            "input": [
                {"role": "user", "content": "Task"},
                {"role": "user", "content": json.dumps(context)},
            ],
        },
        "context_path": ("input", 1, "content"),
        "expected_scope": scope,
        "target_context": target,
        "model_name": "model",
        "model_version": "model-version",
    }


def refresh(arguments):
    c = arguments["response"]["context"]
    arguments["response"]["context_digest"] = _digest(c)
    arguments["request"]["input"][1]["content"] = json.dumps(c)


def test_full_exact_request_and_references_survive_mutation():
    args = fixture()
    prepared = ExperienceRequest(**args)
    manifest = prepared.evidence_manifest()
    assert manifest["references"][0]["digest"] == "sha256:" + "b" * 64
    args["request"]["input"][0]["content"] = "later mutation"
    seen = []
    result = prepared.dispatch(lambda body: seen.append(body) or "result")
    assert result == "result" and type(seen[0]) is bytes
    assert json.loads(seen[0])["input"][0]["content"] == "Task"
    assert (
        manifest["prompt"]["digest"] == "sha256:" + hashlib.sha256(seen[0]).hexdigest()
    )
    manifest["references"].clear()
    assert len(prepared.evidence_manifest()["references"]) == 1
    assert prepared.audit_metadata()["dispatch_attempted"] is True
    assert prepared.audit_metadata()["provider_consumption_verified"] is False


@pytest.mark.parametrize("changed", ["context", "scope", "target", "payload"])
def test_mismatched_binding_rejected(changed):
    args = fixture()
    if changed == "context":
        args["response"]["context"]["lessons"][0]["lesson"] = "changed"
    if changed == "scope":
        args["expected_scope"] = {"policy_key": "other"}
    if changed == "target":
        args["target_context"] = {"stateful": 1}
    if changed == "payload":
        args["request"]["input"][1]["content"] = "{}"
    with pytest.raises(ValueError):
        ExperienceRequest(**args)


@pytest.mark.parametrize("role", ["system", "developer"])
def test_memory_cannot_be_inserted_as_privileged_instructions(role):
    args = fixture()
    args["request"]["input"][1]["role"] = role
    with pytest.raises(ValueError, match="privileged"):
        ExperienceRequest(**args)


def test_empty_context_is_valid_without_made_up_references():
    args = fixture()
    args["response"]["context"]["lessons"] = []
    args["response"]["no_match"] = True
    refresh(args)
    assert ExperienceRequest(**args).evidence_manifest()["references"] == []


@pytest.mark.parametrize(
    "field",
    ["authorization_granted", "actor_exposure_verified", "revalidation_required"],
)
def test_unexpected_assurance_flags_rejected(field):
    args = fixture()
    args["response"][field] = not args["response"][field]
    with pytest.raises(ValueError):
        ExperienceRequest(**args)


def test_timeout_never_automatically_replays_an_unknown_model_call():
    prepared = ExperienceRequest(**fixture())
    calls = []

    def uncertain(body):
        calls.append(body)
        raise TimeoutError("unknown result")

    with pytest.raises(TimeoutError):
        prepared.dispatch(uncertain)
    with pytest.raises(RuntimeError, match="already attempted"):
        prepared.dispatch(uncertain)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_async_dispatch_is_bound_and_cannot_be_repeated():
    prepared = ExperienceRequest(**fixture())

    async def send(body):
        return hashlib.sha256(body).hexdigest()

    checksum = await prepared.dispatch_async(send)
    assert checksum == prepared.audit_metadata()["request_digest"]
    with pytest.raises(RuntimeError):
        await prepared.dispatch_async(send)


def test_stale_context_and_delayed_dispatch_require_revalidation():
    args = fixture()
    args["response"]["assessed_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=40)
    ).isoformat()
    with pytest.raises(ValueError, match="stale"):
        ExperienceRequest(**args)
    prepared = ExperienceRequest(**fixture())
    prepared._assessed_at -= timedelta(seconds=40)
    with pytest.raises(ValueError, match="stale"):
        prepared.dispatch(lambda body: None)
    assert prepared.audit_metadata()["dispatch_attempted"] is False


@pytest.mark.parametrize("change", ["duplicate", "digest", "truth", "trust"])
def test_invalid_lesson_entries_fail_closed(change):
    args = fixture()
    lessons = args["response"]["context"]["lessons"]
    if change == "duplicate":
        lessons.append(lessons[0].copy())
    if change == "digest":
        lessons[0]["record_digest"] = "wrong"
    if change == "truth":
        lessons[0]["lesson_truth_verified"] = True
    if change == "trust":
        lessons[0]["trust"] = "verified_instruction"
    refresh(args)
    with pytest.raises(ValueError):
        ExperienceRequest(**args)
