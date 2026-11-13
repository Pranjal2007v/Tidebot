import json

import pytest

from tidebot.installations import (InstallationsError, ai_clients, load_installations,
                                   parse_installations)

ENTRY = {"ai_url": "https://api.example.com/v1", "ai_model": "small-model"}


def parse(data):
    return parse_installations(json.dumps(data))


def test_entries_are_keyed_by_installation_number():
    got = parse({"123": ENTRY, "456": {**ENTRY, "ai_key": " zq-key-7 "}})
    assert got == {123: ENTRY, 456: {**ENTRY, "ai_key": "zq-key-7"}}


def test_an_empty_file_has_no_installations():
    assert parse({}) == {}


def test_an_empty_key_counts_as_no_key():
    assert parse({"1": {**ENTRY, "ai_key": ""}}) == {1: ENTRY}


@pytest.mark.parametrize("text, message", [
    ("{not json", "the installations file is not JSON"),
    ("[]", "the installations file must be an object keyed by installation id"),
    ('{"acme": {}}', "installation ids are numbers, but one key is not"),
    ('{"-5": {}}', "installation ids are numbers, but one key is not"),
    ('{"1": "small-model"}', "installation 1 must be an object"),
    ('{"1": {"ai_url": "https://a.example/v1"}}', "installation 1 is missing ai_model"),
    ('{"1": {"ai_key": "k"}}', "installation 1 is missing ai_url and ai_model"),
    ('{"1": {"ai_url": "u", "ai_model": "   "}}', "installation 1 is missing ai_model"),
    ('{"1": {"ai_url": "u", "ai_model": 4}}', "installation 1: ai_model must be text"),
    ('{"1": {"ai_url": "u", "ai_model": "m", "model": "x", "ai_uri": "y"}}',
     "installation 1 has unknown keys: ai_uri, model"),
])
def test_what_is_wrong_is_named(text, message):
    with pytest.raises(InstallationsError) as err:
        parse_installations(text)
    assert str(err.value) == message


def test_errors_never_hold_a_value():
    secret = "zq-key-7"
    for entry in ({"ai_key": secret}, {**ENTRY, "ai_key": secret, secret: "x"},
                  {"ai_url": secret, "ai_model": 4}):
        with pytest.raises(InstallationsError) as err:
            parse({"1": entry})
        # An unknown key's name is shown so a typo can be found; values never are.
        assert secret not in str(err.value).replace("unknown keys: " + secret, "")


def test_load_reads_the_file(tmp_path):
    path = tmp_path / "installations.json"
    path.write_text(json.dumps({"9": ENTRY}))
    assert load_installations(path) == {9: ENTRY}


def test_load_says_when_the_file_cannot_be_read(tmp_path):
    path = tmp_path / "missing.json"
    with pytest.raises(InstallationsError) as err:
        load_installations(path)
    assert str(err.value) == f"can't read the installations file at {path}"


def test_each_installation_gets_its_own_client():
    clients = ai_clients(parse({"1": ENTRY, "2": {"ai_url": "http://localhost:11434/v1/",
                                                 "ai_model": "local", "ai_key": "k"}}))
    assert sorted(clients) == [1, 2]
    assert clients[1].url == "https://api.example.com/v1/chat/completions"
    assert (clients[1].model, clients[1].key) == ("small-model", None)
    assert clients[2].url == "http://localhost:11434/v1/chat/completions"
    assert (clients[2].model, clients[2].key) == ("local", "k")
