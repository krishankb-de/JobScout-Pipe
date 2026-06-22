"""Lever — public unauthenticated JSON API: api.lever.co/v0/postings/{client}."""
from __future__ import annotations

from ..models import ATSType, CompanyEntity, RawJob
from ..normalize import clean_ws, epoch_ms_to_dt, strip_html
from .base import BaseExtractor


class LeverExtractor(BaseExtractor):
    ats = ATSType.LEVER

    async def extract(self, company: CompanyEntity) -> list[RawJob]:
        client = self.resolve_meta(company).get("client")
        if not client:
            return []
        url = f"https://api.lever.co/v0/postings/{client}?mode=json"
        data = await self._get_json(url)
        if not isinstance(data, list):
            return []
        jobs: list[RawJob] = []
        for p in data:
            cats = p.get("categories") or {}
            apply_url = p.get("applyUrl") or p.get("hostedUrl")
            title = clean_ws(p.get("text"))
            if not apply_url or not title:
                continue
            jobs.append(RawJob(
                company=company.name,
                title=title,
                apply_url=apply_url,
                listing_url=p.get("hostedUrl", ""),
                location=clean_ws(cats.get("location")),
                description=strip_html(p.get("descriptionPlain") or p.get("description")),
                posted_at=epoch_ms_to_dt(p.get("createdAt")),
                source_ats=ATSType.LEVER,
                employment_type=clean_ws(cats.get("commitment")),
                workplace_type=clean_ws(p.get("workplaceType")),
                department=clean_ws(cats.get("team") or cats.get("department")),
                job_id=str(p.get("id", "")),
            ))
        return jobs
