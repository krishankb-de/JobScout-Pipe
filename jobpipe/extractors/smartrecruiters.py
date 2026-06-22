"""SmartRecruiters — public Posting API: api.smartrecruiters.com/v1/companies/{co}/postings."""
from __future__ import annotations

from ..models import ATSType, CompanyEntity, RawJob
from ..normalize import clean_ws, join_nonempty, parse_iso
from .base import BaseExtractor

PAGE = 100
MAX_JOBS = 1000  # politeness cap; SmartRecruiters paginates with offset/limit


class SmartRecruitersExtractor(BaseExtractor):
    ats = ATSType.SMARTRECRUITERS

    async def extract(self, company: CompanyEntity) -> list[RawJob]:
        co = self.resolve_meta(company).get("company")
        if not co:
            return []
        jobs: list[RawJob] = []
        offset = 0
        while offset < MAX_JOBS:
            url = (f"https://api.smartrecruiters.com/v1/companies/{co}/postings"
                   f"?limit={PAGE}&offset={offset}")
            data = await self._get_json(url)
            content = data.get("content") or []
            for j in content:
                title = clean_ws(j.get("name"))
                job_id = str(j.get("id", ""))
                if not title or not job_id:
                    continue
                loc = j.get("location") or {}
                jobs.append(RawJob(
                    company=company.name,
                    title=title,
                    apply_url=f"https://jobs.smartrecruiters.com/{co}/{job_id}",
                    listing_url=f"https://jobs.smartrecruiters.com/{co}/{job_id}",
                    location=join_nonempty(loc.get("city", ""), loc.get("country", "")),
                    posted_at=parse_iso(j.get("releasedDate")),
                    source_ats=ATSType.SMARTRECRUITERS,
                    employment_type=clean_ws((j.get("typeOfEmployment") or {}).get("label")),
                    workplace_type="Remote" if loc.get("remote") else "",
                    department=clean_ws((j.get("department") or {}).get("label")),
                    job_id=job_id,
                ))
            total = data.get("totalFound", 0)
            offset += PAGE
            if offset >= total or not content:
                break
        return jobs
