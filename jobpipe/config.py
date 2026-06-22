"""Runtime configuration via pydantic-settings (env prefix JOBPIPE_, .env file)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JOBPIPE_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Core extraction
    window_hours: int = 48  # keep postings within N hours of now; 0 = keep all
    require_seniority: bool = False  # strict mode: require junior/entry/mid/grad token

    # Concurrency / politeness
    http_concurrency: int = 20
    browser_concurrency: int = 8  # stealth-browser sessions; clamped to <=10 (8GB RAM)
    per_domain_delay: float = 1.5  # min seconds between requests to the same host
    request_timeout: float = 30.0
    workday_max_jobs: int = 400  # cap per Workday tenant (they can hold 1000s)

    # Paths
    seed_csv: Path = Path("data/seed_companies.csv")
    output_xlsx: Path = Path("data/output/jobs.xlsx")
    state_db: Path = Path("data/output/state.sqlite")
    adaptive_db: Path = Path("data/output/adaptive.sqlite")
    keywords: Path = Path("config/keywords.yaml")

    # Optional discovery / proxy (interfaces only; unset by default)
    proxy_urls: list[str] = Field(default_factory=list)
    serp_api_key: str = ""
    serp_provider: str = "serpapi"

    user_agents: list[str] = Field(default_factory=lambda: list(DEFAULT_USER_AGENTS))

    @field_validator("window_hours")
    @classmethod
    def _non_negative_window(cls, v: int) -> int:
        if v < 0:
            raise ValueError("window_hours must be >= 0 (0 disables the freshness filter)")
        return v

    @field_validator("browser_concurrency")
    @classmethod
    def _clamp_browser(cls, v: int) -> int:
        # Hard ceiling: >10 concurrent stealth Chromium sessions exhausts 8GB RAM.
        return max(1, min(int(v), 10))

    @field_validator("http_concurrency")
    @classmethod
    def _positive_http(cls, v: int) -> int:
        return max(1, int(v))

    @field_validator("proxy_urls", mode="before")
    @classmethod
    def _split_proxies(cls, v):
        # Accept a comma-separated string from the environment.
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @property
    def keep_all(self) -> bool:
        return self.window_hours == 0


@lru_cache
def get_settings() -> Settings:
    return Settings()
