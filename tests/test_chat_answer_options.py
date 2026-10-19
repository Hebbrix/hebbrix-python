"""MemoryChat exposes the reply-phrasing fields of /v1/chat/completions.

answer_style ("natural" by default on the server, or "quote") and
no_information_reply are sent only when set, so the server defaults apply and
older servers see the same request as before.
"""

from unittest.mock import Mock, patch

import pytest
from hebbrix.chat import MemoryChat


def _response():
    response = Mock()
    response.json.return_value = {
        "choices": [{"message": {"content": "You live in Varnhold."}}],
        "memory_context": {"answer_composition": "composed_from_sources"},
        "usage": {},
        "model": "test",
    }
    return response


@pytest.mark.parametrize("method", ["send", "send_with_context"])
def test_answer_options_are_sent_only_when_set(method):
    chat = MemoryChat(api_key="local-test", model="test")
    with patch("hebbrix.chat.requests.post", return_value=_response()) as post:
        getattr(chat, method)("Where do I live?", "s")
        getattr(chat, method)(
            "Where do I live?",
            "s",
            answer_style="quote",
            no_information_reply="Not on file yet.",
        )
    default, explicit = (call.kwargs["json"] for call in post.call_args_list)
    assert "answer_style" not in default and "no_information_reply" not in default
    assert explicit["answer_style"] == "quote"
    assert explicit["no_information_reply"] == "Not on file yet."


@pytest.mark.parametrize(
    "options",
    [
        {"answer_style": "verbatim"},
        {"answer_style": ""},
        {"no_information_reply": ""},
        {"no_information_reply": "x" * 501},
        {"no_information_reply": 3},
    ],
)
def test_invalid_answer_options_fail_before_the_request(options):
    chat = MemoryChat(api_key="local-test", model="test")
    with patch("hebbrix.chat.requests.post") as post:
        with pytest.raises(ValueError):
            chat.send("Where do I live?", "s", **options)
    post.assert_not_called()
