"""Greenhouse — public Job Board API: boards-api.greenhouse.io/v1/boards/{token}/jobs."""
from __future__ import annotations

from ..models import ATSType, CompanyEntity, RawJob
from ..normalize import clean_ws, join_nonempty, parse_iso, strip_html
from .base import BaseExtractor


class GreenhouseExtractor(BaseExtractor):
    ats = ATSType.GREENHOUSE

    async def extract(self, company: CompanyEntity) -> list[RawJob]:
        token = self.resolve_meta(company).get("token")
        if not token or "$" in token:  # skip template placeholders like ${ghSlug}
            return []
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
        data = await self._get_json(url)
        jobs: list[RawJob] = []
        for j in data.get("jobs", []):
            title = clean_ws(j.get("title"))
            apply_url = j.get("absolute_url")
            if not title or not apply_url:
                continue
            loc = (j.get("location") or {}).get("name", "")
            depts = ", ".join(d.get("name", "") for d in (j.get("departments") or []) if d.get("name"))
            jobs.append(RawJob(
                company=company.name,
                title=title,
                apply_url=apply_url,
                listing_url=apply_url,
                location=clean_ws(loc),
                description=strip_html(j.get("content")),
                posted_at=parse_iso(j.get("first_published") or j.get("updated_at")),
                source_ats=ATSType.GREENHOUSE,
                department=clean_ws(depts),
                job_id=str(j.get("id", "")),
            ))
        return jobs
