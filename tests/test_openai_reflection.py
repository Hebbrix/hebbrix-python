"""Offline adapter regressions. No external calls or real credentials."""

import json

import httpx
import pytest
from hebbrix.experience import _json
from hebbrix.openai_reflection import OpenAIReflectionAdapter


def adapter(**changes):
    return OpenAIReflectionAdapter(
        **{
            "api_key": "not-a-real-secret",
            "model": "pinned-model",
            "input_usd_per_million": "1.75",
            "output_usd_per_million": "14",
            "reservation_microusd": 100000,
            **changes,
        }
    )


def source(**changes):
    return {
        "model": "pinned-model",
        "provider_budget_microusd": 100000,
        "authorization_granted": False,
        **changes,
    }


def response(**changes):
    return {
        "model": "pinned-model",
        "status": "completed",
        "usage": {"input_tokens": 200, "output_tokens": 100},
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {
                                "hypotheses": [],
                                "insufficient_evidence_reason": "No diagnostic evidence",
                            }
                        ),
                    }
                ],
            }
        ],
        **changes,
    }


def install_transport(value, handler):
    value.close()
    value._client = httpx.Client(
        base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handler)
    )


def test_prepared_bytes_cost_and_single_attempt():
    value, seen = adapter(), []

    def handler(request):
        seen.append(request.content)
        return httpx.Response(200, json=response())

    install_transport(value, handler)
    try:
        request, path = value.prepare(source())
        assert (
            path == ("input", 0, "content")
            and request["store"] is False
            and "tools" not in request
        )
        result = value.send_json_bytes(_json(request))
        assert result.reported_microusd == 1750 and len(seen) == 1
        with pytest.raises(ValueError):
            value.send_json_bytes(_json(request))
        assert len(seen) == 1
    finally:
        value.close()


@pytest.mark.parametrize(
    "kind", ["status", "body", "usage", "model", "cost", "multiple", "transport"]
)
def test_incomplete_or_ambiguous_response_retains_uncertainty_without_leaking(kind):
    value, calls = adapter(), []

    def handler(request):
        calls.append(request)
        if kind == "transport":
            raise RuntimeError("secret provider diagnostic")
        data = response()
        if kind == "status":
            return httpx.Response(429, json={"secret": "private"})
        if kind == "body":
            return httpx.Response(200, text="secret invalid body")
        if kind == "usage":
            data["usage"]["input_tokens"] = True
        if kind == "model":
            data["model"] = "different-model"
        if kind == "cost":
            data["usage"]["output_tokens"] = 100000
        if kind == "multiple":
            data["output"] *= 2
        return httpx.Response(200, json=data)

    install_transport(value, handler)
    try:
        request, _ = value.prepare(source())
        with pytest.raises(RuntimeError, match="reconciliation") as raised:
            value.send_json_bytes(_json(request))
        assert "secret" not in str(raised.value)
        with pytest.raises(ValueError):
            value.send_json_bytes(_json(request))
        assert len(calls) == 1
    finally:
        value.close()


@pytest.mark.parametrize("mutation", ["budget", "input", "model", "request"])
def test_boundaries_are_checked_before_any_provider_call(mutation):
    value = adapter()
    install_transport(value, lambda _: pytest.fail("no external call allowed"))
    try:
        data = source()
        if mutation == "budget":
            data["provider_budget_microusd"] += 1
        if mutation == "model":
            data["model"] = "different-model"
        if mutation == "input":
            data["padding"] = "x" * 128001
        with pytest.raises(ValueError):
            request, _ = value.prepare(data)
            if mutation == "request":
                request["tools"] = [{"type": "web_search"}]
                value.send_json_bytes(_json(request))
    finally:
        value.close()
