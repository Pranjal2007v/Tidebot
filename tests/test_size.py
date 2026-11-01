from tidebot.size import changed_lines, size_label, stale_labels


def test_buckets():
    assert [size_label(n) for n in (0, 9, 10, 29, 30, 99, 100, 499, 500, 5000)] == [
        "size/XS", "size/XS", "size/S", "size/S", "size/M", "size/M",
        "size/L", "size/L", "size/XL", "size/XL"]


def test_changed_lines_adds_both_sides():
    assert changed_lines({"additions": 12, "deletions": 3}) == 15
    assert changed_lines({}) == 0


def test_stale_labels_keeps_other_labels():
    assert stale_labels(["bug", "size/XS", "size/L", "size/M"], "size/M") == ["size/L", "size/XS"]
