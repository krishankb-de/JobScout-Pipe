"""Join.com — public API: join.com/api/public/companies/{company_id}/jobs.

Requires the integer company_id (discovery responsibility). Given one (via
ats_meta['company_id']), paginates the public feed. Returns [] without an id.
"""
from __future__ import annotations

from ..models import ATSType, CompanyEntity, RawJob
from ..normalize import clean_ws, join_nonempty, parse_iso
from .base import BaseExtractor

PAGE = 100


def _emp_type(j: dict) -> str:
    et = j.get("employmentType")
    if isinstance(et, dict):
        return clean_ws(et.get("name") or et.get("label"))
    return ""


class JoinExtractor(BaseExtractor):
    ats = ATSType.JOIN

    async def extract(self, company: CompanyEntity) -> list[RawJob]:
        cid = self.resolve_meta(company).get("company_id") or (company.ats_meta or {}).get("company_id")
        if not cid:
            return []
        jobs: list[RawJob] = []
        page = 1
        while True:
            url = f"https://join.com/api/public/companies/{cid}/jobs?page={page}&pageSize={PAGE}"
            data = await self._get_json(url)
            items = data.get("items") or []
            for j in items:
                title = clean_ws(j.get("title"))
                id_param = j.get("idParam") or str(j.get("id", ""))
                if not title or not id_param:
                    continue
                city = j.get("city") or {}
                jobs.append(RawJob(
                    company=company.name,
                    title=title,
                    apply_url=f"https://join.com/jobs/{id_param}",
                    listing_url=f"https://join.com/jobs/{id_param}",
                    location=join_nonempty(city.get("cityName", ""), city.get("countryName", "")),
                    posted_at=parse_iso(j.get("createdAt")),
                    source_ats=ATSType.JOIN,
                    employment_type=_emp_type(j),
                    workplace_type=clean_ws(j.get("workplaceType")).title(),
                    job_id=str(j.get("id", "")),
                ))
            pg = data.get("pagination") or {}
            if page >= pg.get("pageCount", 0) or not items:
                break
            page += 1
        return jobs
