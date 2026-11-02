from tidebot.help import help_text


def test_anyone_sees_only_open_commands():
    text = help_text("alice", None)
    assert "anyone access" in text
    assert "`/ask`" in text and "`/help`" in text
    assert "`/merge`" not in text and "`/lgtm`" not in text
    assert "**Workflow:**" not in text
    assert "need more access" in text


def test_collaborator_sees_triage_commands():
    text = help_text("bob", "triage")
    assert "`/lgtm`" in text and "`/assign`" in text and "`/remind`" in text
    assert "`/merge`" not in text


def test_maintainer_sees_everything():
    text = help_text("carol", "admin")
    assert "`/merge`" in text and "`/label`" in text
    assert "need more access" not in text


def test_welcome_lists_every_group():
    from tidebot.help import welcome_text
    text = welcome_text("dave")
    assert text.startswith("Thanks for the pull request, @dave!")
    assert "**AI:**" in text and "**Workflow:**" in text and "**Community:**" in text
    assert "`/merge`" in text and "`/ask`" in text and "`:tide /help`" in text
