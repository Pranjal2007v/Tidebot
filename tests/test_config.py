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
