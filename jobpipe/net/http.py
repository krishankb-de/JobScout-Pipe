"""Shared httpx client factory + a throttled, retrying client wrapper.

`ThrottledClient` is drop-in for extractors (exposes async get/post returning
httpx.Response): it applies per-domain throttling, rotates the User-Agent, and
retries transient network errors / 429 / 5xx with exponential backoff.
"""
from __future__ import annotations

import itertools
import random

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import DEFAULT_USER_AGENTS
from .throttle import PerDomainThrottle


class TransientHTTPError(Exception):
    """Retryable response status (429 / 5xx)."""


def build_client(*, timeout: float = 30.0, proxy: str | None = None,
                 user_agent: str | None = None) -> httpx.AsyncClient:
    headers = {
        "User-Agent": user_agent or DEFAULT_USER_AGENTS[0],
        "Accept-Encoding": "gzip, deflate",
    }
    kwargs: dict = {"follow_redirects": True, "timeout": timeout, "headers": headers}
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.AsyncClient(**kwargs)


class ThrottledClient:
    def __init__(self, client: httpx.AsyncClient, *, throttle: PerDomainThrottle | None = None,
                 retries: int = 2, user_agents: list[str] | None = None):
        self._client = client
        self._throttle = throttle
        self._retries = retries
        self._uas = list(user_agents or DEFAULT_USER_AGENTS)
        self._ua_cycle = itertools.cycle(self._uas)

    async def get(self, url: str, **kw) -> httpx.Response:
        return await self._request("GET", url, **kw)

    async def post(self, url: str, **kw) -> httpx.Response:
        return await self._request("POST", url, **kw)

    async def _request(self, method: str, url: str, **kw) -> httpx.Response:
        if self._throttle is not None:
            await self._throttle.wait(url)
        headers = {"User-Agent": next(self._ua_cycle), **(kw.pop("headers", {}) or {})}
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._retries + 1),
            wait=wait_exponential(multiplier=0.5, max=8),
            retry=retry_if_exception_type((httpx.TransportError, TransientHTTPError)),
            reraise=True,
        ):
            with attempt:
                resp = await self._client.request(method, url, headers=headers, **kw)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise TransientHTTPError(f"{resp.status_code} {url}")
                return resp
        raise RuntimeError("unreachable")  # pragma: no cover

    async def aclose(self) -> None:
        await self._client.aclose()
