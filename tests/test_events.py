from tidebot.config import TideConfig
from tidebot.events import (claim_issue, claims_issue, issue_opened, label_size,
                            pull_request_opened, pull_request_pushed)
from tidebot.github import GitHubError


class FakeGitHub:
    def __init__(self):
        self.calls = []

    def post_comment(self, repo, number, body):
        self.calls.append(("post_comment", repo, number, body))

    def add_labels(self, repo, number, labels):
        self.calls.append(("add_labels", repo, number, list(labels)))

    def remove_label(self, repo, number, label):
        self.calls.append(("remove_label", repo, number, label))

    def add_assignees(self, repo, number, logins):
        self.calls.append(("add_assignees", repo, number, list(logins)))


def pr(**fields):
    data = {"number": 7, "user": {"login": "alice"}, "title": "Add retry to the webhook client",
            "body": "Retries 5xx answers twice before giving up.", "additions": 3,
            "deletions": 1, "labels": []}
    data.update(fields)
    return data


def test_new_pr_gets_a_welcome():
    gh = FakeGitHub()
    pull_request_opened(gh, "o/r", pr(), TideConfig(size_labels=False, pr_lint=False))
    (call,) = gh.calls
    assert call[:3] == ("post_comment", "o/r", 7)
    assert call[3].startswith("Thanks for the pull request, @alice!")


def test_bot_prs_get_a_size_label_but_no_welcome():
    gh = FakeGitHub()
    pull_request_opened(gh, "o/r", pr(user={"login": "dependabot[bot]"}), TideConfig())
    assert gh.calls == [("add_labels", "o/r", 7, ["size/XS"])]


def test_new_pr_is_labeled_by_size():
    gh = FakeGitHub()
    pull_request_opened(gh, "o/r", pr(additions=40, deletions=5), TideConfig(pr_lint=False))
    assert gh.calls[0] == ("add_labels", "o/r", 7, ["size/M"])
    assert gh.calls[1][0] == "post_comment"


def test_size_labels_off_in_config():
    gh = FakeGitHub()
    pull_request_pushed(gh, "o/r", pr(additions=600), TideConfig(size_labels=False))
    assert gh.calls == []


def test_push_swaps_the_old_size_label():
    gh = FakeGitHub()
    pull_request_pushed(gh, "o/r", pr(additions=150, labels=[{"name": "size/S"}, {"name": "bug"}]),
                        TideConfig())
    assert gh.calls == [("remove_label", "o/r", 7, "size/S"),
                        ("add_labels", "o/r", 7, ["size/L"])]


def test_right_label_already_there_does_nothing():
    gh = FakeGitHub()
    label_size(gh, "o/r", pr(additions=2, labels=[{"name": "size/XS"}]))
    assert gh.calls == []


def test_lint_notes_join_the_welcome():
    gh = FakeGitHub()
    pull_request_opened(gh, "o/r", pr(title="Update app.py", body=""), TideConfig(size_labels=False))
    (_, _, _, body), = gh.calls
    assert body.startswith("Thanks for the pull request")
    assert "GitHub suggested" in body and "Add a description" in body


def test_clean_pr_gets_no_lint_notes():
    gh = FakeGitHub()
    pull_request_opened(gh, "o/r", pr(), TideConfig(size_labels=False))
    assert "help reviewers" not in gh.calls[0][3]


def test_pr_lint_off_in_config():
    gh = FakeGitHub()
    pull_request_opened(gh, "o/r", pr(title="Fix", body=""),
                        TideConfig(size_labels=False, pr_lint=False))
    assert "help reviewers" not in gh.calls[0][3]


def test_new_issue_gets_triage_label():
    gh = FakeGitHub()
    issue_opened(gh, "o/r", {"number": 4}, TideConfig())
    assert gh.calls == [("add_labels", "o/r", 4, ["triage"])]


def test_triage_label_off_in_config():
    gh = FakeGitHub()
    issue_opened(gh, "o/r", {"number": 4}, TideConfig(triage_label=False))
    assert gh.calls == []


def test_claim_phrases():
    assert claims_issue("Hi! I'd like to work on this.")
    assert claims_issue("I\u2019d like to work on this one")
    assert claims_issue("Can I take this?")
    assert claims_issue("please assign it to me")
    assert claims_issue("I would like to work on this issue")


def test_not_claims():
    assert not claims_issue("This breaks when I work on the config")
    assert not claims_issue("> I'd like to work on this\nAre they still on it?")
    assert not claims_issue("```\nI'll take this\n```")
    assert not claims_issue(None)


def test_claim_assigns_and_replies():
    gh = FakeGitHub()
    reply = claim_issue(gh, "o/r", {"number": 4, "assignees": []}, "bob", "Can I work on this?")
    assert gh.calls == [("add_assignees", "o/r", 4, ["bob"])]
    assert reply.startswith("Thanks @bob, this issue is yours")


def test_claim_skips_taken_issues_prs_and_bots():
    gh = FakeGitHub()
    body = "I'd like to work on this"
    assert claim_issue(gh, "o/r", {"number": 4, "assignees": [{"login": "x"}]}, "bob", body) is None
    assert claim_issue(gh, "o/r", {"number": 4, "pull_request": {}}, "bob", body) is None
    assert claim_issue(gh, "o/r", {"number": 4}, "helper[bot]", body) is None
    assert gh.calls == []


def test_refused_assignment_stays_quiet():
    class Refusing(FakeGitHub):
        def add_assignees(self, repo, number, logins):
            raise GitHubError(422, "cannot be assigned")

    assert claim_issue(Refusing(), "o/r", {"number": 4}, "bob", "can I take this?") is None
