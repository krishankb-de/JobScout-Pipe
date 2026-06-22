"""Ashby — public posting API: api.ashbyhq.com/posting-api/job-board/{org}."""
from __future__ import annotations

from ..models import ATSType, CompanyEntity, RawJob
from ..normalize import clean_ws, parse_iso, strip_html
from .base import BaseExtractor


class AshbyExtractor(BaseExtractor):
    ats = ATSType.ASHBY

    async def extract(self, company: CompanyEntity) -> list[RawJob]:
        org = self.resolve_meta(company).get("org")
        if not org:
            return []
        url = f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true"
        data = await self._get_json(url)
        jobs: list[RawJob] = []
        for j in data.get("jobs", []):
            if j.get("isListed") is False:
                continue
            title = clean_ws(j.get("title"))
            apply_url = j.get("applyUrl") or j.get("jobUrl")
            if not title or not apply_url:
                continue
            workplace = clean_ws(j.get("workplaceType")) or ("Remote" if j.get("isRemote") else "")
            jobs.append(RawJob(
                company=company.name,
                title=title,
                apply_url=apply_url,
                listing_url=j.get("jobUrl", ""),
                location=clean_ws(j.get("location")),
                description=strip_html(j.get("descriptionPlain") or j.get("descriptionHtml")),
                posted_at=parse_iso(j.get("publishedAt")),
                source_ats=ATSType.ASHBY,
                employment_type=clean_ws(j.get("employmentType")),
                workplace_type=workplace,
                department=clean_ws(j.get("department") or j.get("team")),
                job_id=str(j.get("id", "")),
            ))
        return jobs
