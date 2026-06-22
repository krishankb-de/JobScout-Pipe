"""Adaptive DOM fallback for bespoke career sites (no standard ATS).

Tries a fast static fetch (Fetcher, browser-impersonation) and escalates to a
stealth browser (StealthyFetcher/camoufox) only when static yields nothing — the
expensive path is gated by a semaphore (>10 concurrent stealth sessions exhausts
8GB RAM). Job cards are located with scrapling's adaptive element tracking:
`auto_save` fingerprints the matched elements into a persistent SQLite DB so that
after a site redesign `adaptive=True` relocates them by structural similarity.

The fingerprint DB MUST live on persistent storage — in serverless deployments
mount a volume, or auto_match is wiped on container exit.
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

from scrapling import Selector
from scrapling.fetchers import AsyncFetcher, StealthyFetcher

from ..models import ATSType, CompanyEntity, RawJob
from ..normalize import abs_url, clean_ws

# Ordered candidate selectors for "job link" elements on unknown layouts.
CANDIDATE_SELECTORS = [
    "a[href*='/jobs/']",
    "a[href*='/job/']",
    "a[href*='/stellen']",
    "a[href*='/position']",
    "a[href*='/vacanc']",
    "a[href*='/karriere/']",
    "a[href*='/career']",
    "[class*='job'] a[href]",
    "[class*='position'] a[href]",
    "[class*='vacanc'] a[href]",
]
_BOT_WALL = ("captcha", "cf-browser-verification", "please enable javascript", "checking your browser")


class DomExtractor:
    ats = ATSType.UNKNOWN

    def __init__(self, *, adaptive_db: str, use_browser: bool = True,
                 browser_semaphore: asyncio.Semaphore | None = None, timeout: float = 30.0):
        self.adaptive_db = str(adaptive_db)
        self.use_browser = use_browser
        self.sem = browser_semaphore
        self.timeout = timeout

    async def extract(self, company: CompanyEntity) -> list[RawJob]:
        url = company.career_url
        html = await self._fetch_static(url)
        jobs = self.parse(html, url, company) if html else []
        if not jobs and self.use_browser and (html is None or self._looks_blocked(html)):
            html = await self._fetch_browser(url)
            if html:
                jobs = self.parse(html, url, company)
        return jobs

    # -- fetching --------------------------------------------------------
    async def _fetch_static(self, url: str) -> str | None:
        try:
            r = await AsyncFetcher.get(url, timeout=int(self.timeout), stealthy_headers=True)
        except Exception:
            return None
        if getattr(r, "status", 0) >= 400:
            return None
        return str(r.html_content or "")

    async def _fetch_browser(self, url: str) -> str | None:
        async def _go() -> str | None:
            try:
                r = await StealthyFetcher.async_fetch(
                    url, headless=True, network_idle=True, timeout=int(self.timeout) * 1000
                )
                return str(r.html_content or "")
            except Exception:
                return None
        if self.sem is not None:
            async with self.sem:
                return await _go()
        return await _go()

    @staticmethod
    def _looks_blocked(html: str) -> bool:
        low = html[:5000].lower()
        return len(html) < 2000 or any(w in low for w in _BOT_WALL)

    # -- adaptive parsing ------------------------------------------------
    def parse(self, html: str, url: str, company: CompanyEntity) -> list[RawJob]:
        if not html:
            return []
        domain = urlsplit(url).hostname or company.name
        sel = Selector(content=html, url=url, adaptive=True,
                       storage_args={"storage_file": self.adaptive_db})
        elements = self._locate(sel, domain)
        jobs: list[RawJob] = []
        seen: set[str] = set()
        for el in elements:
            href = el.attrib.get("href") or ""
            title = clean_ws(el.text) or clean_ws(el.attrib.get("title") or el.attrib.get("aria-label"))
            apply_url = abs_url(url, href)
            if not title or len(title) < 3 or not apply_url.startswith("http"):
                continue
            if apply_url in seen:
                continue
            seen.add(apply_url)
            jobs.append(RawJob(
                company=company.name,
                title=title,
                apply_url=apply_url,
                listing_url=apply_url,
                source_ats=ATSType.UNKNOWN,
            ))
        return jobs

    def _locate(self, sel: Selector, domain: str):
        """Find job cards, fingerprinting on success; relocate adaptively on failure."""
        ident = f"{domain}:jobcards"
        for css in CANDIDATE_SELECTORS:
            try:
                els = sel.css(css, auto_save=True, identifier=ident)
            except Exception:
                els = []
            if els:
                return list(els)
        # Selectors broke (site redesign) -> relocate via saved fingerprints.
        for css in CANDIDATE_SELECTORS:
            try:
                els = sel.css(css, adaptive=True, identifier=ident)
            except Exception:
                els = []
            if els:
                return list(els)
        return []
