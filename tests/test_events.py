from tidebot.config import TideConfig
from tidebot.config import parse_config
from tidebot.events import (assign_reviewers, claim_issue, claims_issue, issue_opened,
                            label_size, pull_request_opened, pull_request_pushed,
                            pull_request_ready)
from tidebot.github import GitHubError


class FakeGitHub:
    def __init__(self, files=None, changed=()):
        self.calls = []
        self.files = files or {}
        self.changed = list(changed)

    def fetch_file(self, repo, path):
        return self.files.get(path)

    def pull_files(self, repo, number):
        return self.changed

    def request_reviewers(self, repo, number, logins, teams=()):
        self.calls.append(("request_reviewers", repo, number, list(logins), list(teams)))

    def repo_labels(self, repo):
        self.calls.append(("repo_labels", repo))
        return ["bug", "enhancement", "documentation", "question", "triage"]

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


CODEOWNERS = "*.py @bob\n/docs/ @carol @org/writers\n"


def test_owners_of_changed_files_are_asked_to_review():
    gh = FakeGitHub({".github/CODEOWNERS": CODEOWNERS}, ["app.py", "docs/x.md"])
    assign_reviewers(gh, "o/r", pr(), TideConfig())
    assert gh.calls == [("request_reviewers", "o/r", 7, ["bob", "carol"], ["writers"])]


def test_tide_yml_reviewers_beat_codeowners():
    gh = FakeGitHub({"CODEOWNERS": CODEOWNERS}, ["app.py"])
    config = parse_config("reviewers:\n  '*.py': [dave]\n")
    assign_reviewers(gh, "o/r", pr(), config)
    assert gh.calls == [("request_reviewers", "o/r", 7, ["dave"], [])]


def test_author_and_already_asked_are_skipped():
    gh = FakeGitHub({"CODEOWNERS": "* @alice @bob @erin\n"}, ["x"])
    assign_reviewers(gh, "o/r", pr(requested_reviewers=[{"login": "Bob"}]), TideConfig())
    assert gh.calls == [("request_reviewers", "o/r", 7, ["erin"], [])]


def test_nothing_to_ask():
    gh = FakeGitHub({"CODEOWNERS": "/docs/ @carol\n"}, ["app.py"])
    assign_reviewers(gh, "o/r", pr(), TideConfig())
    gh_author_only = FakeGitHub({"CODEOWNERS": "* @alice\n"}, ["app.py"])
    assign_reviewers(gh_author_only, "o/r", pr(), TideConfig())
    assert gh.calls == gh_author_only.calls == []


def test_drafts_wait_until_ready():
    gh = FakeGitHub({"CODEOWNERS": CODEOWNERS}, ["app.py"])
    pull_request_opened(gh, "o/r", pr(draft=True), TideConfig(size_labels=False))
    assert [c[0] for c in gh.calls] == ["post_comment"]
    pull_request_ready(gh, "o/r", pr(), TideConfig())
    assert gh.calls[-1] == ("request_reviewers", "o/r", 7, ["bob"], [])


def test_refused_review_request_still_welcomes():
    class Refusing(FakeGitHub):
        def request_reviewers(self, repo, number, logins, teams=()):
            raise GitHubError(422, "not a collaborator")

    gh = Refusing({"CODEOWNERS": CODEOWNERS}, ["app.py"])
    pull_request_opened(gh, "o/r", pr(), TideConfig(size_labels=False))
    assert [c[0] for c in gh.calls] == ["post_comment"]


def test_new_issue_is_labeled_by_content():
    gh = FakeGitHub()
    issue_opened(gh, "o/r", {"number": 4, "title": "Crash in the docs build", "body": ""},
                 TideConfig())
    assert gh.calls == [("repo_labels", "o/r"),
                        ("add_labels", "o/r", 4, ["triage", "bug", "documentation"])]


def test_content_labels_skip_labels_already_set():
    gh = FakeGitHub()
    issue = {"number": 4, "title": "Crash on save", "labels": [{"name": "Bug"}]}
    issue_opened(gh, "o/r", issue, TideConfig(triage_label=False))
    assert gh.calls == [("repo_labels", "o/r")]


def test_auto_label_off_in_config():
    gh = FakeGitHub()
    issue_opened(gh, "o/r", {"number": 4, "title": "Crash on save"},
                 TideConfig(auto_label=False))
    assert gh.calls == [("add_labels", "o/r", 4, ["triage"])]
