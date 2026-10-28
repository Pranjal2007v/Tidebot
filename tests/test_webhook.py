from tidebot.webhook import sign, verify_signature

SECRET = "It's a Secret to Everybody"
BODY = b"Hello, World!"


def test_sign_matches_github_docs_example():
    # Example from GitHub's "Validating webhook deliveries" docs.
    assert sign(SECRET, BODY) == (
        "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17"
    )


def test_valid_signature_passes():
    assert verify_signature(SECRET, BODY, sign(SECRET, BODY))


def test_tampered_body_fails():
    assert not verify_signature(SECRET, b"Hello, World?", sign(SECRET, BODY))


def test_wrong_secret_fails():
    assert not verify_signature("other", BODY, sign(SECRET, BODY))


def test_missing_or_malformed_header_fails():
    assert not verify_signature(SECRET, BODY, None)
    assert not verify_signature(SECRET, BODY, "")
    assert not verify_signature(SECRET, BODY, "sha1=abc")


def test_empty_secret_fails():
    assert not verify_signature("", BODY, sign("", BODY))
