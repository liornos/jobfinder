from __future__ import annotations
import os, yaml
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

@dataclass(slots=True) 
class Defaults: cities: List[str]; keywords: List[str]
@dataclass(slots=True) 
class OutputCfg: csv: Optional[str]=None; sqlite: Optional[str]=None
@dataclass(slots=True) 
class DiscoveryCfg: sources: List[str]; limit: int=50
@dataclass(slots=True) 
class AppConfig:
    defaults: Defaults; output: OutputCfg; discovery: DiscoveryCfg; env: Dict[str, Any]

def load_config(path: Optional[str]=None) -> AppConfig:
    load_dotenv()
    p = Path(path) if path else None
    data: Dict[str, Any] = {}
    if p and p.exists(): data = yaml.safe_load(p.read_text()) or {}
    defaults, output, discovery = data.get("defaults", {}), data.get("output", {}), data.get("discovery", {})
    return AppConfig(
        defaults=Defaults(defaults.get("cities", []), defaults.get("keywords", [])),
        output=OutputCfg(output.get("csv"), output.get("sqlite")),
        discovery=DiscoveryCfg(discovery.get("sources", ["greenhouse","lever"]), int(discovery.get("limit", 50))),
        env=dict(os.environ),
    )
