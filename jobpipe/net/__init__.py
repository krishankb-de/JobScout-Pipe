"""Network layer: throttling, concurrency budgets, proxy rotation, HTTP client."""
from __future__ import annotations

from .http import ThrottledClient, TransientHTTPError, build_client
from .proxy import ProxyRotator
from .throttle import ConcurrencyBudget, PerDomainThrottle

__all__ = [
    "ThrottledClient",
    "TransientHTTPError",
    "build_client",
    "ProxyRotator",
    "ConcurrencyBudget",
    "PerDomainThrottle",
]
