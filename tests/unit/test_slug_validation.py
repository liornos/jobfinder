import pytest

from jobfinder.pipeline import _is_valid_org_slug


@pytest.mark.parametrize(
    "slug",
    [
        "vi",
        "ai",
        "jfrog",
        "catonetworks",
        "paloaltonetworks2",
        "varonis-internal",
        "careersintl-maxlinear",  # valid shape (even if you later drop iCIMS)
        "d-fendsolutions",
    ],
)
def test_slug_valid(slug: str):
    assert _is_valid_org_slug(slug) is True


@pytest.mark.parametrize(
    "slug",
    [
        None,
        "",
        "p",
        "o",
        "www",
        "jobs",
        "careers",
        "apply",
        "search",
        "en",
        "en-us",
        "12",
        "123",  # no letters
        "a1",  # only one letter
        "-bad",
        "bad-",
        "_bad",
        "bad_",
        "bad..name",
        "bad/name",
        "bad name",
    ],
)
def test_slug_invalid(slug):
    assert _is_valid_org_slug(slug) is False
