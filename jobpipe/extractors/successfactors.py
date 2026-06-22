"""SAP SuccessFactors — CSRF-token + POST /services/recruiting/v1/jobs, per-locale.

Best-effort: SuccessFactors deploys CAPTCHAs, locale-isolated requisitions, and
many tenants run legacy Recruiting-Marketing portals without this v1 API. On any
auth/parse/CAPTCHA failure the extractor degrades to [] (caller isolates).
"""
from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from ..models import ATSType, CompanyEntity, RawJob
from ..normalize import clean_ws, parse_iso, strip_html
from .base import BaseExtractor

LOCALES = ("en_US", "de_DE")
PAGE = 100


class SuccessFactorsExtractor(BaseExtractor):
    ats = ATSType.SUCCESSFACTORS

    def _base_url(self, company: CompanyEntity) -> str | None:
        meta = self.resolve_meta(company)
        base = meta.get("base_url") or meta.get("discovered_url") or company.career_url
        sp = urlsplit(base)
        if not sp.hostname:
            return None
        return f"{sp.scheme or 'https'}://{sp.hostname}"

    async def _csrf(self, base: str) -> str | None:
        try:
            r = await self.client.get(
                f"{base}/services/recruiting/v1/jobs",
                headers={"X-CSRF-Token": "Fetch", "Accept": "application/json"},
            )
            return r.headers.get("X-CSRF-Token") or r.headers.get("x-csrf-token")
        except Exception:
            return None

    async def extract(self, company: CompanyEntity) -> list[RawJob]:
        base = self._base_url(company)
        if not base:
            return []
        token = await self._csrf(base)
        if not token:
            return []
        jobs: list[RawJob] = []
        seen: set[str] = set()
        for locale in LOCALES:
            try:
                data = await self._post_json(
                    f"{base}/services/recruiting/v1/jobs",
                    {"locale": locale, "company": "", "pageNumber": 1, "pageSize": PAGE},
                    headers={"X-CSRF-Token": token, "Accept": "application/json"},
                )
            except Exception:
                continue
            for j in data.get("jobs", data.get("requisitions", [])):
                title = clean_ws(j.get("jobTitle") or j.get("title"))
                url = j.get("applyUrl") or j.get("url") or j.get("jobUrl")
                if not title or not url or url in seen:
                    continue
                seen.add(url)
                jobs.append(RawJob(
                    company=company.name,
                    title=title,
                    apply_url=url,
                    location=clean_ws(j.get("location") or j.get("city")),
                    description=strip_html(j.get("jobDescription") or j.get("description")),
                    posted_at=parse_iso(j.get("postedDate") or j.get("postedAt")),
                    source_ats=ATSType.SUCCESSFACTORS,
                    job_id=str(j.get("jobReqId") or j.get("id", "")),
                ))
        return jobs
