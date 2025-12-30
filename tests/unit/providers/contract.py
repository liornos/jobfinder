from __future__ import annotations

from typing import Any, Mapping

REQUIRED_FIELDS = ("id", "title", "company", "url")
OPTIONAL_STR_FIELDS = ("location", "created_at", "description", "provider", "org")


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def assert_normalized_job(job: Mapping[str, Any]) -> None:
    assert isinstance(job, dict)

    missing = [
        field for field in REQUIRED_FIELDS if not _is_non_empty_str(job.get(field))
    ]
    assert not missing, f"missing required fields: {missing}"

    for field in REQUIRED_FIELDS:
        assert isinstance(job[field], str)

    for field in OPTIONAL_STR_FIELDS:
        val = job.get(field)
        if val not in (None, ""):
            assert isinstance(val, str)

    if job.get("remote") is not None:
        assert isinstance(job["remote"], bool)
