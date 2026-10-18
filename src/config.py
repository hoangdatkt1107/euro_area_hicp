from __future__ import annotations
from pydantic_settings import BaseSettings
from pathlib import Path
from pdb import set_trace

PROJECT_ROOT = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    project_root: Path = PROJECT_ROOT
    # Important paths for Medallion Architecture (hierarchical data layout)
    data: Path = PROJECT_ROOT / "data"
    bronze: Path = data / "bronze"
    silver: Path = data / "silver"
    gold: Path = data / "gold"

    dashboard_data = project_root / "dashboard" / "data"