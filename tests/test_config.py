from tidebot.config import TideConfig, parse_config

README_EXAMPLE = """\
auto_label: true
size_labels: true
star_gate: false
triage_label: true
pr_lint: true
"""


def test_readme_example_parses():
    assert parse_config(README_EXAMPLE) == TideConfig()


def test_empty_or_missing_file_gives_defaults():
    assert parse_config(None) == TideConfig()
    assert parse_config("") == TideConfig()


def test_overrides():
    cfg = parse_config("star_gate: true\npr_lint: false\n")
    assert cfg.star_gate is True
    assert cfg.pr_lint is False
    assert cfg.auto_label is True


def test_unknown_keys_ignored():
    assert parse_config("nonsense: 1\n") == TideConfig()


def test_wrong_types_fall_back_to_defaults():
    cfg = parse_config("star_gate: 'yes please'\nsize_labels: 0\n")
    assert cfg == TideConfig()


def test_invalid_yaml_gives_defaults():
    assert parse_config("auto_label: [unclosed") == TideConfig()


def test_non_mapping_gives_defaults():
    assert parse_config("- a\n- b\n") == TideConfig()


def test_reviewers_map():
    cfg = parse_config("reviewers:\n  docs/: [alice, '@bob']\n  '*.py': carol\n")
    assert cfg.reviewers == (("docs/", ("@alice", "@bob")), ("*.py", ("@carol",)))


def test_bad_reviewers_entries_are_skipped():
    cfg = parse_config("reviewers:\n  docs/: 3\n  src/: [dave, 7]\n")
    assert cfg.reviewers == (("src/", ("@dave",)),)
    assert parse_config("reviewers: [a, b]\n").reviewers == ()


def test_every_switch_has_help_and_matches_the_defaults():
    from tidebot.config import options
    names = [o.name for o in options()]
    assert names[:5] == ["auto_label", "size_labels", "star_gate", "triage_label", "pr_lint"]
    assert "reviewers" not in names
    for option in options():
        assert option.help.endswith(".")
        assert getattr(TideConfig(), option.name) is option.default


def test_to_yaml_round_trips():
    from tidebot.config import to_yaml
    assert parse_config(to_yaml(TideConfig())) == TideConfig()
    cfg = parse_config("star_gate: true\npr_lint: false\n"
                       "reviewers:\n  docs/: [alice]\n  '*.py': ['@org/backend', bob]\n")
    text = to_yaml(cfg)
    assert "star_gate: true\n" in text and "pr_lint: false\n" in text
    assert parse_config(text) == cfg


def test_default_yaml_lists_every_switch_and_no_reviewers():
    from tidebot.config import options, to_yaml
    text = to_yaml(TideConfig())
    assert text.count("\n") == len(options())
    assert "reviewers" not in text
