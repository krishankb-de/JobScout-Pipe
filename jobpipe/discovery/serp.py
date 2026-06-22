"""SERP-based career-page discovery (interface only — needs a SERP API key).

Production flow (see PLAN.md): for each company name from the Handelsregister,
query a SERP API (e.g. `"{name}" careers OR jobs`) to find the employer's direct
career/ATS domain, bypassing aggregator sites. Wire `Settings.serp_api_key` /
`serp_provider` to enable.
"""
from __future__ import annotations

from collections.abc import Iterator

from ..models import CompanyEntity
from .base import DiscoveryNotConfigured, DiscoveryProvider


class SerpDiscovery(DiscoveryProvider):
    name = "serp"

    def __init__(self, company_names, *, api_key: str = "", provider: str = "serpapi"):
        self.company_names = list(company_names)
        self.api_key = api_key
        self.provider = provider

    def __iter__(self) -> Iterator[CompanyEntity]:
        if not self.api_key:
            raise DiscoveryNotConfigured(
                "SERP discovery needs an API key. Set JOBPIPE_SERP_API_KEY (and "
                "JOBPIPE_SERP_PROVIDER), or use CsvSeedDiscovery for the seed list."
            )
        raise DiscoveryNotConfigured(  # pragma: no cover - implementation stub
            f"SERP provider {self.provider!r} integration not implemented in this build."
        )
