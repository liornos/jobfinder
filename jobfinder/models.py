from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, Iterable
from datetime import datetime

@dataclass(frozen=True, slots=True)
class Company:
    name: str
    city: Optional[str]=None
    provider: Optional[str]=None
    org: Optional[str]=None
    careers_url: Optional[str]=None
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True, slots=True)
class Job:
    id: str
    title: str
    company: str
    url: str
    location: Optional[str]=None
    remote: Optional[bool]=None
    created_at: Optional[datetime]=None
    provider: Optional[str]=None
    extra: Optional[Dict[str, Any]]=None
    def to_row(self) -> Dict[str, Any]:
        d=asdict(self); d['created_at']=self.created_at.isoformat() if self.created_at else None; return d
