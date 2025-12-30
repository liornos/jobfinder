from __future__ import annotations

from jobfinder import filtering


def test_filter_by_title_keywords_matches_case_insensitive_substrings():
    rows = [
        {"id": "1", "title": "Senior QA Engineer"},
        {"id": "2", "title": "DevOps Lead"},
        {"id": "3", "title": "Software engineer"},
    ]

    filtered = filtering.filter_by_title_keywords(rows, ["QA", "ENGINEER"])

    assert [r["id"] for r in filtered] == ["1", "3"]


def test_filter_by_title_keywords_returns_all_when_empty():
    rows = [
        {"id": "1", "title": "Senior QA Engineer"},
        {"id": "2", "title": "DevOps Lead"},
    ]

    filtered = filtering.filter_by_title_keywords(rows, [])

    assert filtered == rows
