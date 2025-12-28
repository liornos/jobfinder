# file: jobfinder/providers/__init__.py
"""
Provider modules expose a single function:
    fetch_jobs(org: str, *[, limit, ...]) -> list[dict]

Modules available:
  - greenhouse, lever, smartrecruiters, ashby
  - breezy, comeet, workday, recruitee, jobvite, icims, workable
Why minimal: importing submodules must not execute heavy logic here.
"""

__all__ = [
    "greenhouse",
    "lever",
    "smartrecruiters",
    "ashby",
    "breezy",
    "comeet",
    "workday",
    "recruitee",
    "jobvite",
    "icims",
    "workable",
]
