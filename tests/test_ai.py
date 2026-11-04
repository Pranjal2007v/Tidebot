import json

import httpx
import pytest

from tidebot.ai import AIClient, AIError, ai_from_env


def client(handler, key="k", url="https://models.example/v1/"):
    calls = []

    def transport(request):
        calls.append(request)
        return handler(request)

    return calls, AIClient(url, "small-model", key,
                           httpx.Client(transport=httpx.MockTransport(transport)))


def answer(text):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant",
                                                              "content": text}}]})


def test_complete_posts_chat_request_and_returns_text():
    calls, ai = client(lambda r: answer("  Auth lives in app.py.\n"))
    text = ai.ask("You help maintainers.", "where is auth handled?")
    assert text == "Auth lives in app.py."
    req = calls[0]
    assert str(req.url) == "https://models.example/v1/chat/completions"
    assert req.headers["Authorization"] == "Bearer k"
    body = json.loads(req.content)
    assert body["model"] == "small-model"
    assert body["messages"] == [{"role": "system", "content": "You help maintainers."},
                                {"role": "user", "content": "where is auth handled?"}]
    assert body["max_tokens"] == 800


def test_full_endpoint_url_and_no_key():
    calls, ai = client(lambda r: answer("ok"), key=None,
                       url="http://localhost:8080/v1/chat/completions")
    ai.ask("s", "u")
    assert str(calls[0].url) == "http://localhost:8080/v1/chat/completions"
    assert "Authorization" not in calls[0].headers


@pytest.mark.parametrize("response, message", [
    (httpx.Response(500, text="boom"), "the model endpoint answered 500"),
    (httpx.Response(429, text="slow down"), r"busy \(rate limited\)"),
    (httpx.Response(200, text="not json"), "could not read"),
    (httpx.Response(200, json={"choices": []}), "could not read"),
    (httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]}), "empty answer"),
])
def test_bad_answers_raise_ai_error(response, message):
    _, ai = client(lambda r: response)
    with pytest.raises(AIError, match=message):
        ai.ask("s", "u")


def test_timeouts_and_network_errors_raise_ai_error():
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    def down(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(AIError, match="too long"):
        client(slow)[1].ask("s", "u")
    with pytest.raises(AIError, match="could not be reached"):
        client(down)[1].ask("s", "u")


def test_error_messages_never_include_the_key():
    _, ai = client(lambda r: httpx.Response(401, text="bad key k-secret"), key="k-secret")
    with pytest.raises(AIError) as err:
        ai.ask("s", "u")
    assert "k-secret" not in str(err.value)


def test_ai_from_env():
    assert ai_from_env({}) is None
    assert ai_from_env({"TIDEBOT_AI_URL": "https://x/v1"}) is None
    ai = ai_from_env({"TIDEBOT_AI_URL": "https://x/v1", "TIDEBOT_AI_MODEL": "m",
                      "TIDEBOT_AI_KEY": " key "})
    assert ai.url == "https://x/v1/chat/completions"
    assert ai.model == "m" and ai.key == "key"
    assert ai_from_env({"TIDEBOT_AI_URL": "https://x/v1", "TIDEBOT_AI_MODEL": "m"}).key is None
