from __future__ import annotations
import re
from typing import List, Tuple
from .models import Job
try: from rapidfuzz import fuzz
except Exception: fuzz = None
def normalize(s: str) -> str: return re.sub(r"\s+", " ", s.strip().lower())
def score(job: Job, keywords: List[str], cities: List[str]) -> Tuple[int, List[str]]:
    s=0; reasons=[]; t=normalize(job.title); loc=normalize(job.location or ""); desc=normalize((job.extra or {}).get("description","")[:1000])
    for kw in keywords:
        k=normalize(kw)
        if k in t: s+=20; reasons.append(f"title:{k}")
        if k and fuzz: s+=int(0.2*fuzz.partial_ratio(k,t)); s+=int(0.1*fuzz.partial_ratio(k,desc))
    if cities and any(normalize(c) in loc for c in cities): s+=15; reasons.append("city")
    if job.remote: s+=5; reasons.append("remote")
    return s,reasons
