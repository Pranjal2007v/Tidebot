from tidebot.config import TideConfig
from tidebot.events import pull_request_opened


class FakeGitHub:
    def __init__(self):
        self.calls = []

    def post_comment(self, repo, number, body):
        self.calls.append(("post_comment", repo, number, body))

    def add_labels(self, repo, number, labels):
        self.calls.append(("add_labels", repo, number, list(labels)))

    def remove_label(self, repo, number, label):
        self.calls.append(("remove_label", repo, number, label))


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


def test_bot_prs_are_left_alone():
    gh = FakeGitHub()
    pull_request_opened(gh, "o/r", pr(user={"login": "dependabot[bot]"}), TideConfig())
    assert gh.calls == []
