from tidebot.commands import Command
from tidebot.workflow import Target, run_command

ISSUE = Target("o/r", 5, is_pr=False, author="alice")
PR = Target("o/r", 6, is_pr=True, author="alice")


class FakeGitHub:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name,) + tuple(list(a) if isinstance(a, (list, tuple)) else a
                                              for a in args))
        return record


def run(target, name, args=""):
    gh = FakeGitHub()
    reply = run_command(gh, target, Command(name, args))
    return gh.calls, reply


def test_label_adds_and_removes():
    calls, reply = run(ISSUE, "label", "bug, docs -triage")
    assert calls == [
        ("add_labels", "o/r", 5, ["bug", "docs"]),
        ("remove_label", "o/r", 5, "triage"),
    ]
    assert reply is None


def test_label_without_args_shows_usage():
    calls, reply = run(ISSUE, "label")
    assert calls == []
    assert "Usage" in reply


def test_close_and_reopen():
    assert run(ISSUE, "close")[0] == [("set_state", "o/r", 5, "closed")]
    assert run(ISSUE, "reopen")[0] == [("set_state", "o/r", 5, "open")]


def test_assign_defaults_to_author():
    assert run(ISSUE, "assign")[0] == [("add_assignees", "o/r", 5, ["alice"])]
    assert run(ISSUE, "assign", "@me")[0] == [("add_assignees", "o/r", 5, ["alice"])]


def test_assign_others():
    assert run(ISSUE, "assign", "@bob carol")[0] == [("add_assignees", "o/r", 5, ["bob", "carol"])]


def test_cc_requests_review_on_pr():
    calls, reply = run(PR, "cc", "@bob")
    assert calls == [("request_reviewers", "o/r", 6, ["bob"])]
    assert reply is None


def test_cc_on_issue_mentions():
    calls, reply = run(ISSUE, "cc", "bob @carol")
    assert calls == []
    assert reply == "cc @bob @carol"


def test_commands_without_handler_do_nothing():
    assert run(ISSUE, "merge") == ([], None)
