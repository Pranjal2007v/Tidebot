from tidebot.config import TideConfig
from tidebot.events import label_size, pull_request_opened, pull_request_pushed


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
