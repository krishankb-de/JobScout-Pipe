"""Workday — hidden CXS JSON API: POST /wday/cxs/{tenant}/{site}/jobs.

Listing-level extraction only (title, location, relative postedOn, public URL):
descriptions/exact dates require a per-job detail GET, which the orchestrator can
request lazily for matched titles. Enforces a polite inter-page delay and a cap;
fragments by facet when a tenant exceeds Workday's hard 2,000-result limit.
"""
from __future__ import annotations

import asyncio

import httpx

from ..models import ATSType, CompanyEntity, RawJob
from ..normalize import clean_ws
from .base import BaseExtractor

PAGE = 20  # Workday's max page size for the jobs endpoint
HARD_CAP = 2000  # Workday refuses offsets beyond ~2000 for a single query


class WorkdayExtractor(BaseExtractor):
    ats = ATSType.WORKDAY

    def __init__(self, client: httpx.AsyncClient, *, delay: float = 1.5, max_jobs: int = 600):
        super().__init__(client)
        self.delay = delay
        self.max_jobs = max_jobs

    def _host(self, meta: dict) -> str | None:
        tenant, shard = meta.get("tenant"), meta.get("shard")
        if not tenant or not shard:
            return None
        return f"{tenant}.{shard}.myworkdayjobs.com"

    async def extract(self, company: CompanyEntity) -> list[RawJob]:
        meta = self.resolve_meta(company)
        host = self._host(meta)
        site = meta.get("site")
        if not host or not site:
            return []
        endpoint = f"https://{host}/wday/cxs/{meta['tenant']}/{site}/jobs"

        first = await self._page(endpoint, {}, 0)
        total = first.get("total", 0)
        out: list[RawJob] = self._to_jobs(first, company, host, site)

        if total > HARD_CAP:
            return await self._fragment_by_facet(endpoint, first, company, host, site)

        offset = PAGE
        while offset < min(total, self.max_jobs):
            await asyncio.sleep(self.delay)
            page = await self._page(endpoint, {}, offset)
            batch = self._to_jobs(page, company, host, site)
            if not batch:
                break
            out.extend(batch)
            offset += PAGE
        return out

    async def _page(self, endpoint: str, facets: dict, offset: int) -> dict:
        payload = {"appliedFacets": facets, "limit": PAGE, "offset": offset, "searchText": ""}
        return await self._post_json(endpoint, payload)

    def _to_jobs(self, data: dict, company: CompanyEntity, host: str, site: str) -> list[RawJob]:
        jobs: list[RawJob] = []
        for jp in data.get("jobPostings", []):
            title = clean_ws(jp.get("title"))
            path = jp.get("externalPath") or ""
            if not title or not path:
                continue
            jobs.append(RawJob(
                company=company.name,
                title=title,
                apply_url=f"https://{host}/{site}{path}",
                listing_url=f"https://{host}/{site}{path}",
                location=clean_ws(jp.get("locationsText")),
                posted_at_text=clean_ws(jp.get("postedOn")),
                source_ats=ATSType.WORKDAY,
                job_id=path.rsplit("_", 1)[-1] if "_" in path else "",
            ))
        return jobs

    async def _fragment_by_facet(self, endpoint, first, company, host, site) -> list[RawJob]:
        """When total > 2000, query each value of the largest facet separately."""
        seen: set[str] = set()
        out: list[RawJob] = []
        facets = first.get("facets") or []
        # Pick the facet with the most values (usually location).
        best = max(facets, key=lambda f: len(f.get("values", [])), default=None)
        if not best:
            return self._to_jobs(first, company, host, site)
        fid = best.get("facetParameter")
        for val in best.get("values", []):
            vid = val.get("id")
            if not vid:
                continue
            offset = 0
            while offset < min(val.get("count", PAGE), self.max_jobs, HARD_CAP):
                await asyncio.sleep(self.delay)
                try:
                    page = await self._page(endpoint, {fid: [vid]}, offset)
                except Exception:
                    break
                batch = self._to_jobs(page, company, host, site)
                for j in batch:
                    if j.apply_url not in seen:
                        seen.add(j.apply_url)
                        out.append(j)
                if len(batch) < PAGE:
                    break
                offset += PAGE
            if len(out) >= self.max_jobs:
                break
        return out
