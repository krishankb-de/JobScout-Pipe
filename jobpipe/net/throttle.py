"""Per-domain rate limiting and split HTTP/browser concurrency budgets."""
from __future__ import annotations

import asyncio
from urllib.parse import urlsplit


class PerDomainThrottle:
    """Enforce a minimum interval between requests to the same host (politeness)."""

    def __init__(self, min_interval: float = 1.5):
        self.min_interval = min_interval
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, host: str) -> asyncio.Lock:
        lock = self._locks.get(host)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[host] = lock
        return lock

    async def wait(self, url: str) -> None:
        host = (urlsplit(url).hostname or "").lower()
        if not host or self.min_interval <= 0:
            return
        loop = asyncio.get_event_loop()
        async with self._lock(host):
            elapsed = loop.time() - self._last.get(host, 0.0)
            delay = self.min_interval - elapsed
            if delay > 0:
                await asyncio.sleep(delay)
            self._last[host] = loop.time()


class ConcurrencyBudget:
    """Separate semaphores: many cheap HTTP requests, few expensive stealth browsers."""

    def __init__(self, http: int = 20, browser: int = 8):
        self.http = asyncio.Semaphore(max(1, http))
        self.browser = asyncio.Semaphore(max(1, min(browser, 10)))  # 8GB RAM ceiling
