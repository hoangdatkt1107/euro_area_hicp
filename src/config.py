from __future__ import annotations
from pydantic_settings import BaseSettings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    project_root: Path = PROJECT_ROOT
    # Important paths for Medallion Architecture (hierarchical data layout)
    data: Path = PROJECT_ROOT / "data"
    bronze: Path = PROJECT_ROOT / "data" / "bronze"
    silver: Path = PROJECT_ROOT / "data" / "silver"
    gold: Path = PROJECT_ROOT / "data" / "gold"

    dashboard_data: Path = PROJECT_ROOT / "dashboard" / "data"

    # For httpx pipeline
    retry_status: set[int] = {429, 500, 502, 503, 504}
    max_attempts: int = 5
    backoff_seconds: int = 2

settings = Settings()