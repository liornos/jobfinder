from __future__ import annotations

from jobfinder import pipeline


def test_extract_org_from_comeet_url():
    url = (
        "https://www.comeet.com/jobs/liveu/90.00C/qa-automation-engineer/BB.F51"
        "?coref=1.10.s96_85A"
    )
    assert pipeline._extract_org_from_url("comeet", url) == "liveu"
