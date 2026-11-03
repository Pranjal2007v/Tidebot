from tidebot.owners import owners_for, owners_of, parse_codeowners, split_reviewers

CODEOWNERS = """\
# Default owners
*           @lead
*.py        @bob   # Python
/docs/      @alice docs@example.com
src/api/    @org/backend
**/tests/** @tester
/build/out
"""


def test_parse_skips_comments_and_emails():
    rules = parse_codeowners(CODEOWNERS)
    assert rules[0] == ("*", ("@lead",))
    assert rules[1] == ("*.py", ("@bob",))
    assert rules[2] == ("/docs/", ("@alice",))
    assert rules[-1] == ("/build/out", ())
    assert parse_codeowners(None) == []


def test_last_match_wins():
    rules = parse_codeowners(CODEOWNERS)
    assert owners_of(rules, "README.md") == ("@lead",)
    assert owners_of(rules, "tidebot/app.py") == ("@bob",)
    assert owners_of(rules, "docs/setup.py") == ("@alice",)
    assert owners_of(rules, "src/api/routes.go") == ("@org/backend",)
    assert owners_of(rules, "src/api/tests/x.go") == ("@tester",)


def test_rule_without_owners_clears_ownership():
    rules = parse_codeowners(CODEOWNERS)
    assert owners_of(rules, "build/out/app.js") == ()


def test_anchoring():
    rules = [("/docs/", ("@a",)), ("api/", ("@b",)), ("src/lib", ("@c",))]
    assert owners_of(rules, "docs/x.md") == ("@a",)
    assert owners_of(rules, "pkg/docs/x.md") == ()
    # A pattern ending in a slash, with no other slash, matches at any depth.
    assert owners_of(rules, "pkg/api/x.go") == ("@b",)
    # An inner slash anchors to the root.
    assert owners_of(rules, "src/lib/x.c") == ("@c",)
    assert owners_of(rules, "vendor/src/lib/x.c") == ()


def test_star_stays_in_one_segment():
    rules = [("docs/*", ("@a",))]
    assert owners_of(rules, "docs/x.md") == ("@a",)
    # CODEOWNERS docs/* covers only files directly in docs.
    assert owners_of(rules, "docs/guide/x.md") == ()
    assert owners_of(rules, "other/docs/x.md") == ()
    assert owners_of([("docs/**", ("@a",))], "docs/guide/x.md") == ("@a",)


def test_directory_pattern_needs_a_directory():
    rules = [("app/", ("@a",))]
    assert owners_of(rules, "app") == ()
    assert owners_of(rules, "app/main.py") == ("@a",)


def test_owners_for_many_files_dedupes():
    rules = parse_codeowners(CODEOWNERS)
    assert owners_for(rules, ["a.py", "b.py", "docs/x.md", "README.md"]) == [
        "@bob", "@alice", "@lead"]


def test_split_reviewers_drops_author_and_finds_teams():
    users, teams = split_reviewers(["@Alice", "@bob", "@org/backend"], "alice")
    assert users == ["bob"]
    assert teams == ["backend"]
