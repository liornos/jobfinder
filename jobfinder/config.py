from __future__ import annotations
import os, yaml
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

@dataclass(slots=True)
class Defaults:
    cities: List[str]
    keywords: List[str]

@dataclass(slots=True)
class OutputCfg:
    csv: Optional[str] = None
    sqlite: Optional[str] = None

@dataclass(slots=True)
class DiscoveryCfg:
    sources: List[str]
    limit: int = 50

@dataclass(slots=True)
class AppConfig:
    defaults: Defaults
    output: OutputCfg
    discovery: DiscoveryCfg
    env: Dict[str, Any]

def load_config(path: Optional[str] = None) -> AppConfig:
    load_dotenv()
    cfg_path = Path(path) if path else None
    data: Dict[str, Any] = {}
    if cfg_path and cfg_path.exists():
        data = yaml.safe_load(cfg_path.read_text()) or {}

    defaults = data.get("defaults", {}) or {}
    output = data.get("output", {}) or {}
    discovery = data.get("discovery", {}) or {}

    # Defaults if not provided by user config:
    cities = defaults.get("cities") or ["Tel Aviv", "herzliya"]
    keywords = defaults.get("keywords") or ["software"]
    sources = discovery.get("sources") or [
        "greenhouse",
        "lever",
        "ashby",
        "smartrecruiters",
        "comeet",
        "workable",
        "breezy",
        "workday",
        "recruitee",
        "jobvite",
        "icims",
    ]
    limit = int(discovery.get("limit", 50))

    return AppConfig(
        defaults=Defaults(cities, keywords),
        output=OutputCfg(output.get("csv"), output.get("sqlite")),
        discovery=DiscoveryCfg(sources, limit),
        env=dict(os.environ),
    )
