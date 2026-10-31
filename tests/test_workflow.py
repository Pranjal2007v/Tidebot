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
    assert run(ISSUE, "vote") == ([], None)


def test_lgtm_labels_pr():
    calls, reply = run(PR, "lgtm")
    assert calls == [("add_labels", "o/r", 6, ["lgtm"])]
    assert reply is None


def test_lgtm_cancel_removes_label():
    assert run(PR, "lgtm", "cancel")[0] == [("remove_label", "o/r", 6, "lgtm")]


def test_lgtm_on_issue_is_refused():
    calls, reply = run(ISSUE, "lgtm")
    assert calls == []
    assert "pull requests" in reply


def test_hold_and_wip_toggle_labels():
    assert run(PR, "hold")[0] == [("add_labels", "o/r", 6, ["do-not-merge/hold"])]
    assert run(PR, "hold", "Cancel")[0] == [("remove_label", "o/r", 6, "do-not-merge/hold")]
    assert run(ISSUE, "wip")[0] == [("add_labels", "o/r", 5, ["do-not-merge/wip"])]
    assert run(ISSUE, "wip", "cancel")[0] == [("remove_label", "o/r", 5, "do-not-merge/wip")]


def test_hold_with_reason_still_holds():
    assert run(PR, "hold", "waiting on design review")[0] == [
        ("add_labels", "o/r", 6, ["do-not-merge/hold"])]


def test_retitle():
    assert run(ISSUE, "retitle", " Crash on start ")[0] == [("set_title", "o/r", 5, "Crash on start")]
    calls, reply = run(ISSUE, "retitle")
    assert calls == [] and "Usage" in reply


def test_lock_with_and_without_reason():
    assert run(ISSUE, "lock")[0] == [("lock", "o/r", 5, None)]
    assert run(ISSUE, "lock", "Too heated")[0] == [("lock", "o/r", 5, "too heated")]
    assert run(ISSUE, "lock", "cancel")[0] == [("unlock", "o/r", 5)]


def test_lock_rejects_unknown_reason():
    calls, reply = run(ISSUE, "lock", "boring")
    assert calls == []
    assert "`spam`" in reply


class MilestoneGitHub(FakeGitHub):
    def find_milestone(self, repo, title):
        self.calls.append(("find_milestone", repo, title))
        return 3 if title.lower() == "v1.0" else None


def test_milestone_sets_found_milestone():
    gh = MilestoneGitHub()
    assert run_command(gh, ISSUE, Command("milestone", "V1.0")) is None
    assert gh.calls == [("find_milestone", "o/r", "V1.0"), ("set_milestone", "o/r", 5, 3)]


def test_milestone_unknown_and_clear():
    gh = MilestoneGitHub()
    reply = run_command(gh, ISSUE, Command("milestone", "v9"))
    assert "no open milestone" in reply
    assert gh.calls == [("find_milestone", "o/r", "v9")]
    assert run(ISSUE, "milestone", "clear")[0] == [("set_milestone", "o/r", 5, None)]


def test_duplicate_labels_closes_and_links():
    calls, reply = run(ISSUE, "duplicate", "#2")
    assert calls == [("add_labels", "o/r", 5, ["duplicate"]), ("set_state", "o/r", 5, "closed")]
    assert reply == "Duplicate of #2"
    assert run(ISSUE, "duplicate", "2")[1] == "Duplicate of #2"


def test_duplicate_needs_another_issue():
    assert run(ISSUE, "duplicate")[0] == []
    assert "Usage" in run(ISSUE, "duplicate", "that one")[1]
    assert "itself" in run(ISSUE, "duplicate", "#5")[1]


class MergeGitHub(FakeGitHub):
    def __init__(self, pr=None, reviews=None, ci="success"):
        super().__init__()
        self.pr = {"state": "open", "draft": False, "mergeable": True, "labels": [],
                   "head": {"sha": "abc"}, **(pr or {})}
        self.reviews = {"bob": "APPROVED"} if reviews is None else reviews
        self.ci = ci

    def pull(self, repo, number):
        return self.pr

    def review_states(self, repo, number):
        return self.reviews

    def ci_state(self, repo, sha):
        return self.ci


def merge(gh, args=""):
    return run_command(gh, PR, Command("merge", args))


def test_approve_posts_review_on_pr_only():
    calls, reply = run(PR, "approve")
    assert calls == [("approve", "o/r", 6, "Approved by @alice with `/approve`.")]
    assert reply is None
    assert "pull requests" in run(ISSUE, "approve")[1]


def test_merge_when_green_and_approved():
    gh = MergeGitHub()
    assert merge(gh, "squash") is None
    assert gh.calls == [("merge", "o/r", 6, "abc", "squash")]


def test_merge_lists_every_blocker():
    gh = MergeGitHub(pr={"draft": True, "mergeable": False,
                         "labels": [{"name": "do-not-merge/hold"}]},
                     reviews={}, ci="pending")
    reply = merge(gh)
    assert gh.calls == []
    for part in ("draft", "do-not-merge/hold", "conflicts", "no approval", "still running"):
        assert part in reply


def test_merge_blocked_by_requested_changes_and_failing_ci():
    gh = MergeGitHub(reviews={"bob": "APPROVED", "carol": "CHANGES_REQUESTED"}, ci="failure")
    reply = merge(gh)
    assert "requested changes" in reply and "CI is failing" in reply
    assert "no approval" not in reply


def test_merge_needs_ci_results():
    assert "no CI" in merge(MergeGitHub(ci="none"))


def test_merge_rejects_unknown_method_and_issues():
    assert "Usage" in merge(MergeGitHub(), "yolo")
    assert "pull requests" in run(ISSUE, "merge")[1]
