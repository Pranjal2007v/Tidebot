import io

import pytest

from tidebot.doctor import ERROR, OFF, ON, check, main

PEM = "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----\n"


@pytest.fixture
def env(tmp_path):
    key = tmp_path / "app.pem"
    key.write_text(PEM)
    installs = tmp_path / "installations.json"
    installs.write_text('{"7": {"ai_url": "https://b.example/v1", "ai_model": "theirs", '
                        '"ai_key": "zq-their-key-4"}}')
    return {
        "TIDEBOT_WEBHOOK_SECRET": "s3cret",
        "TIDEBOT_STATE": str(tmp_path / "state.json"),
        "TIDEBOT_APP_ID": "123",
        "TIDEBOT_PRIVATE_KEY": str(key),
        "TIDEBOT_AI_URL": "https://api.example.com/v1",
        "TIDEBOT_AI_MODEL": "small-model",
        "TIDEBOT_INSTALLATIONS": str(installs),
        "TIDEBOT_STATS_TOKEN": "zq-stats-91",
        "TIDEBOT_DASHBOARD_ORIGINS": "https://tidebot.example.com",
        "TIDEBOT_GITHUB_CLIENT_ID": "cid",
        "TIDEBOT_GITHUB_CLIENT_SECRET": "csecret",
        "TIDEBOT_PUBLIC_URL": "https://bot.example.com/",
    }


def status(env):
    return {c.feature: c.status for c in check(env)}


def test_everything_set_up_is_on(env):
    assert set(status(env).values()) == {ON}
    signin = [c for c in check(env) if c.feature == "sign-in"][0]
    assert signin.message == "callback is https://bot.example.com/auth/callback"


def test_only_the_secret_leaves_the_rest_off(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert status({"TIDEBOT_WEBHOOK_SECRET": "s"}) == {
        "webhook": ON, "state": ON, "replies": OFF, "ai": OFF, "installations": OFF,
        "stats token": OFF, "dashboard": OFF, "sign-in": OFF}


def test_missing_secret_is_an_error(env):
    del env["TIDEBOT_WEBHOOK_SECRET"]
    assert status(env)["webhook"] == ERROR


def test_state_folder_must_exist(env, tmp_path):
    env["TIDEBOT_STATE"] = str(tmp_path / "nope" / "state.json")
    assert status(env)["state"] == ERROR


def test_half_a_group_names_what_is_missing(env):
    del env["TIDEBOT_AI_MODEL"]
    ai = [c for c in check(env) if c.feature == "ai"][0]
    assert ai.status == ERROR and ai.message == "also set TIDEBOT_AI_MODEL"


def test_ai_key_alone_is_an_error(env):
    del env["TIDEBOT_AI_URL"], env["TIDEBOT_AI_MODEL"]
    env["TIDEBOT_AI_KEY"] = "k"
    assert status(env)["ai"] == ERROR


def test_private_key_must_be_readable_and_a_pem(env, tmp_path):
    env["TIDEBOT_PRIVATE_KEY"] = str(tmp_path / "missing.pem")
    assert status(env)["replies"] == ERROR
    other = tmp_path / "other.txt"
    other.write_text("hello")
    env["TIDEBOT_PRIVATE_KEY"] = str(other)
    assert status(env)["replies"] == ERROR


@pytest.mark.parametrize("origin", ["tidebot.example.com", "https://a.example/dashboard",
                                    "ftp://a.example"])
def test_origins_must_be_sites(env, origin):
    env["TIDEBOT_DASHBOARD_ORIGINS"] = "https://ok.example, " + origin
    assert status(env)["dashboard"] == ERROR


def test_sign_in_needs_https_and_a_dashboard(env):
    env["TIDEBOT_PUBLIC_URL"] = "http://bot.example.com"
    assert status(env)["sign-in"] == ERROR
    env["TIDEBOT_PUBLIC_URL"] = "https://bot.example.com"
    env["TIDEBOT_DASHBOARD_ORIGINS"] = ""
    assert status(env)["sign-in"] == ERROR


def test_main_exits_1_on_errors_and_never_prints_secrets(env):
    out = io.StringIO()
    assert main(env, out) == 0
    for secret in ("s3cret", "zq-stats-91", "csecret", "zq-their-key-4"):
        assert secret not in out.getvalue()
    del env["TIDEBOT_WEBHOOK_SECRET"]
    assert main(env, io.StringIO()) == 1


def installations(env):
    return [c for c in check(env) if c.feature == "installations"][0]


def test_installations_line_counts_them_and_says_what_the_rest_get(env, tmp_path):
    assert installations(env).message == ("1 installation uses its own model; "
                                          "the rest use small-model")
    (tmp_path / "installations.json").write_text(
        '{"7": {"ai_url": "u", "ai_model": "m"}, "8": {"ai_url": "u", "ai_model": "m"}}')
    del env["TIDEBOT_AI_URL"], env["TIDEBOT_AI_MODEL"]
    assert installations(env) == ("installations", ON, "2 installations use their own model; "
                                                       "the rest have no AI commands")


def test_a_wrong_installations_file_is_an_error(env, tmp_path):
    (tmp_path / "installations.json").write_text('{"7": {"ai_url": "u", "ai_key": "zq-k"}}')
    line = installations(env)
    assert line == ("installations", ERROR, "installation 7 is missing ai_model")
    env["TIDEBOT_INSTALLATIONS"] = str(tmp_path / "gone.json")
    assert installations(env).status == ERROR
    assert main(env, io.StringIO()) == 1
