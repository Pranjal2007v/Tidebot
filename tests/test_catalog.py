from tidebot.catalog import entries, tiers
from tidebot.commands import ALL_COMMANDS, TRIGGER, parse_commands


def test_every_command_is_described_once():
    names = [e.name for e in entries()]
    assert sorted(names) == sorted(ALL_COMMANDS)


def test_examples_parse_back_to_their_own_command():
    for entry in entries():
        assert entry.example.startswith(f"{TRIGGER} /{entry.name}")
        parsed = parse_commands(entry.example)
        assert [c.name for c in parsed] == [entry.name], entry.example


def test_tiers_come_from_the_permission_table():
    by_name = {e.name: e for e in entries()}
    assert by_name["ask"].tier == "Anyone"
    assert by_name["lgtm"].tier == "Collaborator"
    assert by_name["merge"].tier == "Maintainer"
    assert "Collaborator" in by_name["assign"].tier and "Maintainer" in by_name["assign"].tier
    assert tiers() == ["Anyone", "Collaborator", "Maintainer"]


def test_groups_follow_the_readme_order():
    groups = []
    for entry in entries():
        if entry.group not in groups:
            groups.append(entry.group)
    assert groups == ["AI", "Workflow", "Community"]


def test_only_lgtm_is_bare():
    assert [e.name for e in entries() if e.bare] == ["lgtm"]


def test_summaries_and_results_are_filled_in():
    for entry in entries():
        assert entry.summary.endswith(".") and entry.result, entry.name
