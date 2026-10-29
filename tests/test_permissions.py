import pytest

from tidebot.commands import ALL_COMMANDS, Command
from tidebot.permissions import Tier, check, required_tier, tier_for


@pytest.mark.parametrize("permission, tier", [
    ("admin", Tier.MAINTAINER),
    ("maintain", Tier.MAINTAINER),
    ("WRITE", Tier.MAINTAINER),
    ("triage", Tier.COLLABORATOR),
    ("read", Tier.ANYONE),
    ("none", Tier.ANYONE),
    (None, Tier.ANYONE),
])
def test_tier_for(permission, tier):
    assert tier_for(permission) == tier


def test_every_command_has_a_tier():
    for name in ALL_COMMANDS:
        assert isinstance(required_tier(Command(name), "alice"), Tier)


def test_readme_tiers():
    assert required_tier(Command("ask"), "a") == Tier.ANYONE
    assert required_tier(Command("help"), "a") == Tier.ANYONE
    assert required_tier(Command("lgtm"), "a") == Tier.COLLABORATOR
    assert required_tier(Command("remind"), "a") == Tier.COLLABORATOR
    assert required_tier(Command("merge"), "a") == Tier.MAINTAINER
    assert required_tier(Command("milestone"), "a") == Tier.MAINTAINER


@pytest.mark.parametrize("args", ["", "@me", "me", "@Alice", "alice"])
def test_self_assign_needs_collaborator(args):
    assert required_tier(Command("assign", args), "alice") == Tier.COLLABORATOR


@pytest.mark.parametrize("args", ["@bob", "@alice @bob"])
def test_assigning_others_needs_maintainer(args):
    assert required_tier(Command("assign", args), "alice") == Tier.MAINTAINER


def test_check_allows_and_denies():
    assert check(Command("ask"), "a", "read").allowed
    assert check(Command("lgtm"), "a", "triage").allowed
    assert check(Command("merge"), "a", "admin").allowed
    denied = check(Command("merge"), "a", "triage")
    assert not denied.allowed
    assert "maintainer" in denied.reason


def test_unknown_command_is_denied():
    decision = check(Command("teleport"), "a", "admin")
    assert not decision.allowed
    assert "unknown" in decision.reason


def test_star_gate():
    assert not check(Command("ask"), "a", "read", starred=False, star_gate=True).allowed
    assert check(Command("ask"), "a", "read", starred=True, star_gate=True).allowed
    # Collaborators and up skip the gate.
    assert check(Command("ask"), "a", "triage", starred=False, star_gate=True).allowed
