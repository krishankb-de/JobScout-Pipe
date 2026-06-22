"""Thread-safe proxy rotator. No-op by default (direct connection).

Wire a pool via Settings.proxy_urls (env JOBPIPE_PROXY_URLS, comma-separated).
For CAPTCHA-heavy targets (e.g. SuccessFactors), populate with residential
proxies that carry higher IP-reputation scores.
"""
from __future__ import annotations

import threading


class ProxyRotator:
    def __init__(self, proxies: list[str] | None = None):
        self._proxies = [p for p in (proxies or []) if p]
        self._i = 0
        self._lock = threading.Lock()

    def __bool__(self) -> bool:
        return bool(self._proxies)

    def __len__(self) -> int:
        return len(self._proxies)

    def next(self) -> str | None:
        """Round-robin the next proxy URL, or None when no pool is configured."""
        if not self._proxies:
            return None
        with self._lock:
            proxy = self._proxies[self._i % len(self._proxies)]
            self._i += 1
            return proxy
