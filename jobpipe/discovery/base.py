"""Discovery provider interface: yield CompanyEntity targets to crawl."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from ..models import CompanyEntity


class DiscoveryNotConfigured(RuntimeError):
    """Raised by optional providers (SERP, Handelsregister) that need credentials."""


class DiscoveryProvider(ABC):
    name: str = "discovery"

    @abstractmethod
    def __iter__(self) -> Iterator[CompanyEntity]:
        ...
