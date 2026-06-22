"""Handelsregister corporate discovery (interface only).

Production flow (see PLAN.md): iterate the sequentially numbered Gazette notices
(Handelsregisterbekanntmachungen, free since 2022-08-01), parse the unstructured
text to extract Amtsgericht, HRB/HRA number, and legal form, building the ~2.3M
active-company universe. Company names then feed SerpDiscovery to find career
domains. Enabling requires live access + a parser; disabled in this build.
"""
from __future__ import annotations

from collections.abc import Iterator

from ..models import CompanyEntity
from .base import DiscoveryNotConfigured, DiscoveryProvider


class HandelsregisterDiscovery(DiscoveryProvider):
    name = "handelsregister"

    def __init__(self, *, enabled: bool = False, start_index: int = 0, max_notices: int = 0):
        self.enabled = enabled
        self.start_index = start_index
        self.max_notices = max_notices

    def __iter__(self) -> Iterator[CompanyEntity]:
        if not self.enabled:
            raise DiscoveryNotConfigured(
                "Handelsregister gazette crawling is disabled in this build. It "
                "yields company names only; pair with SerpDiscovery to resolve "
                "career URLs. Use CsvSeedDiscovery for the provided seed list."
            )
        raise DiscoveryNotConfigured(  # pragma: no cover - implementation stub
            "Handelsregister notice parser not implemented in this build."
        )
