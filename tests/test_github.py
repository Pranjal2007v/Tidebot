import json

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from tidebot.github import AppAuth, GitHubClient, GitHubError


def recorder(handler):
    calls = []

    def transport(request):
        calls.append(request)
        return handler(request)

    return calls, httpx.Client(transport=httpx.MockTransport(transport))


def client(handler):
    calls, http = recorder(handler)
    return calls, GitHubClient(lambda: "tok", http)


def test_post_comment_sends_token_and_body():
    calls, gh = client(lambda r: httpx.Response(201, json={}))
    gh.post_comment("o/r", 7, "hi")
    req = calls[0]
    assert req.method == "POST"
    assert req.url.path == "/repos/o/r/issues/7/comments"
    assert req.headers["Authorization"] == "token tok"
    assert json.loads(req.content) == {"body": "hi"}


def test_errors_raise():
    _, gh = client(lambda r: httpx.Response(403, text="nope"))
    with pytest.raises(GitHubError) as err:
        gh.set_state("o/r", 1, "closed")
    assert err.value.status == 403


def test_remove_missing_label_is_fine():
    _, gh = client(lambda r: httpx.Response(404))
    gh.remove_label("o/r", 1, "bug")


def test_permission_prefers_role_name():
    _, gh = client(lambda r: httpx.Response(200, json={"permission": "read", "role_name": "triage"}))
    assert gh.permission("o/r", "bob") == "triage"


def test_permission_for_stranger_is_none():
    _, gh = client(lambda r: httpx.Response(404))
    assert gh.permission("o/r", "stranger") is None


def test_has_starred_pages_through_stars():
    def handler(request):
        page = int(request.url.params["page"])
        if page == 1:
            return httpx.Response(200, json=[{"full_name": f"x/{i}"} for i in range(100)])
        return httpx.Response(200, json=[{"full_name": "O/R"}])

    calls, gh = client(handler)
    assert gh.has_starred("alice", "o/r")
    assert len(calls) == 2


def test_has_starred_stops_on_short_page():
    _, gh = client(lambda r: httpx.Response(200, json=[{"full_name": "x/y"}]))
    assert not gh.has_starred("alice", "o/r")


def test_fetch_file():
    calls, gh = client(lambda r: httpx.Response(200, text="star_gate: true\n"))
    assert gh.fetch_file("o/r", ".tide.yml") == "star_gate: true\n"
    assert calls[0].headers["Accept"] == "application/vnd.github.raw+json"
    _, missing = client(lambda r: httpx.Response(404))
    assert missing.fetch_file("o/r", ".tide.yml") is None


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return pem, key.public_key()


def test_app_jwt_is_signed_with_app_key(keypair):
    pem, public = keypair
    token = AppAuth("123", pem, clock=lambda: 1_000_000).app_jwt()
    claims = jwt.decode(token, public, algorithms=["RS256"], options={"verify_exp": False})
    assert claims == {"iat": 999_940, "exp": 1_000_540, "iss": "123"}


def test_installation_token_is_cached_until_near_expiry(keypair):
    pem, _ = keypair
    now = [1_700_000_000.0]
    calls, http = recorder(lambda r: httpx.Response(201, json={
        "token": f"ghs_{len(calls)}", "expires_at": "2023-11-14T23:13:20Z",  # now + 3600
    }))
    auth = AppAuth("1", pem, http=http, clock=lambda: now[0])
    assert auth.installation_token(42) == "ghs_1"
    assert calls[0].url.path == "/app/installations/42/access_tokens"
    assert calls[0].headers["Authorization"].startswith("Bearer ")
    now[0] += 3000
    assert auth.installation_token(42) == "ghs_1"
    now[0] += 600
    assert auth.installation_token(42) == "ghs_2"
