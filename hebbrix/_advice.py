"""Local advisor wire-integrity checks; not authorization or propensity proof."""

import json
import math
import re


def _validate_advisor_scope(policy_key, collection_id, user_id, idempotency_key):
    if (
        type(policy_key) is not str
        or not 1 <= len(policy_key) <= 100
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", policy_key)
    ):
        raise ValueError("policy_key must be an exact valid policy identity")
    for field, value, limit in (
        ("collection_id", collection_id, None),
        ("user_id", user_id, 255),
        ("idempotency_key", idempotency_key, 160),
    ):
        if value is not None and (
            type(value) is not str or (limit is not None and len(value) > limit)
        ):
            raise ValueError(
                "{} must be an immutable string within the API limit".format(field)
            )


def _json_snapshot(value, field, max_bytes):
    def check(item):
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError("{} must contain string JSON keys".format(field))
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        elif type(item) not in (str, int, float, bool, type(None)):
            raise ValueError("{} must contain only JSON values".format(field))

    try:
        check(value)
        encoded = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        if len(encoded.encode("utf-8")) > max_bytes:
            raise ValueError("{} exceeds the API JSON size limit".format(field))
        return json.loads(encoded)
    except (TypeError, OverflowError, RecursionError) as exc:
        raise ValueError(
            "{} must contain finite acyclic JSON values".format(field)
        ) from exc


def _snapshot_advisor_inputs(candidates, context):
    """Detach inputs before the first evidence request/callback, without coercion."""
    if type(context) is not dict:
        raise ValueError("context must be a JSON object")
    if type(candidates) is not list or not 1 <= len(candidates) <= 50:
        raise ValueError("candidates must contain 1-50 distinct actions")
    context_copy = _json_snapshot(context, "context", 16_384)
    candidates_copy = _json_snapshot(candidates, "candidates", 64_000)
    keys = []
    for candidate in candidates_copy:
        if type(candidate) is not dict or set(candidate) - {
            "action_key",
            "description",
            "features",
        }:
            raise ValueError(
                "candidates must contain only action_key, description and features"
            )
        key = candidate.get("action_key")
        if (
            type(key) is not str
            or not 1 <= len(key) <= 160
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", key)
        ):
            raise ValueError(
                "candidate action_key must be an exact valid action identity"
            )
        if key in keys:
            raise ValueError("candidate action_key must be unique")
        if candidate.get("description") is not None and (
            type(candidate["description"]) is not str
            or len(candidate["description"]) > 1000
        ):
            raise ValueError(
                "candidate description must be a string of at most 1000 characters"
            )
        if "features" in candidate and type(candidate["features"]) is not dict:
            raise ValueError("candidate features must be a JSON object")
        keys.append(key)
    return candidates_copy, context_copy, keys


def _validated_advisor_selection(selection, candidate_keys):
    message = (
        "advisor must return the choice and its actual complete logging distribution"
    )
    if type(selection) is not dict or set(selection) != {
        "chosen_action_key",
        "action_probability",
        "behavior_probabilities",
    }:
        raise ValueError(message)
    chosen = selection["chosen_action_key"]
    if type(chosen) is not str or chosen not in candidate_keys:
        raise ValueError("chosen_action_key must be one of the original candidates")
    probabilities = selection["behavior_probabilities"]
    if type(probabilities) is not dict or set(probabilities) != set(candidate_keys):
        raise ValueError(
            "behavior_probabilities must cover exactly all original candidates"
        )

    def probability(value):
        if (
            type(value) not in (int, float)
            or not 0 <= value <= 1
            or not math.isfinite(value)
        ):
            raise ValueError(
                "logging probabilities must be finite numbers in [0, 1], not confidence strings or booleans"
            )
        return value

    detached = {key: probability(probabilities[key]) for key in candidate_keys}
    if not math.isclose(sum(detached.values()), 1.0, abs_tol=1e-8, rel_tol=0):
        raise ValueError(
            "behavior_probabilities must sum to 1; the helper never renormalizes"
        )
    selected_probability = probability(selection["action_probability"])
    if selected_probability <= 0 or detached[chosen] <= 0:
        raise ValueError("chosen action must have a positive logging probability")
    if not math.isclose(
        detached[chosen], selected_probability, abs_tol=1e-8, rel_tol=0
    ):
        raise ValueError(
            "action_probability must match the chosen action's behavior probability"
        )
    return dict(
        chosen_action_key=chosen,
        action_probability=selected_probability,
        behavior_probabilities=detached,
    )
