"""Discovery providers: where the pipeline gets companies to crawl."""
from __future__ import annotations

from .base import DiscoveryNotConfigured, DiscoveryProvider
from .csv_seed import CsvSeedDiscovery
from .handelsregister import HandelsregisterDiscovery
from .serp import SerpDiscovery

__all__ = [
    "DiscoveryNotConfigured",
    "DiscoveryProvider",
    "CsvSeedDiscovery",
    "HandelsregisterDiscovery",
    "SerpDiscovery",
]
