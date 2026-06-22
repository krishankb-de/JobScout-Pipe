"""Extractor base class + shared HTTP helpers.

Each extractor consumes a provider's API/feed and yields `RawJob`s. Extractors
do not own the HTTP client (the orchestrator/net layer provides a configured,
proxied, rate-limited one); for standalone use, pass any httpx.AsyncClient.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from ..classify import classify_url
from ..models import ATSType, CompanyEntity, RawJob

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Encoding": "gzip, deflate",
}


class ExtractorError(Exception):
    """Raised on unrecoverable extraction failure (caller isolates per-company)."""


class BaseExtractor(ABC):
    ats: ATSType = ATSType.UNKNOWN

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    @abstractmethod
    async def extract(self, company: CompanyEntity) -> list[RawJob]:
        ...

    # -- identifier resolution -------------------------------------------
    def resolve_meta(self, company: CompanyEntity) -> dict:
        """Merge ATS identifiers: URL-derived, then probe-supplied ats_meta (wins)."""
        meta = dict(classify_url(company.career_url)[1])
        disc = (company.ats_meta or {}).get("discovered_url")
        if disc:
            meta.update({k: v for k, v in classify_url(disc)[1].items() if v})
        meta.update({k: v for k, v in (company.ats_meta or {}).items() if v})
        return meta

    # -- HTTP helpers ----------------------------------------------------
    async def _get_json(self, url: str, **kw):
        r = await self.client.get(url, headers=DEFAULT_HEADERS, **kw)
        r.raise_for_status()
        return r.json()

    async def _get_text(self, url: str, **kw) -> tuple[int, str, bytes]:
        r = await self.client.get(url, headers=DEFAULT_HEADERS, **kw)
        return r.status_code, r.text, r.content

    async def _post_json(self, url: str, payload: dict, **kw):
        r = await self.client.post(url, json=payload, headers=DEFAULT_HEADERS, **kw)
        r.raise_for_status()
        return r.json()
