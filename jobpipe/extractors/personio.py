"""Personio — public XML feed at {subdomain}.jobs.personio.{de,com}/xml."""
from __future__ import annotations

from lxml import etree

from ..models import ATSType, CompanyEntity, RawJob
from ..normalize import clean_ws, parse_iso, strip_html
from .base import BaseExtractor


class PersonioExtractor(BaseExtractor):
    ats = ATSType.PERSONIO

    async def extract(self, company: CompanyEntity) -> list[RawJob]:
        sub = self.resolve_meta(company).get("subdomain")
        if not sub:
            return []
        content = b""
        base = ""
        for tld in ("de", "com"):
            base = f"https://{sub}.jobs.personio.{tld}"
            status, _, raw = await self._get_text(f"{base}/xml?language=en")
            if status == 200 and b"<position" in raw:
                content = raw
                break
        if not content:
            return []
        try:
            root = etree.fromstring(content)
        except etree.XMLSyntaxError:
            return []

        jobs: list[RawJob] = []
        for pos in root.iter("position"):
            job_id = (pos.findtext("id") or "").strip()
            title = clean_ws(pos.findtext("name"))
            if not job_id or not title:
                continue
            descs = [clean_ws(jd.findtext("value")) for jd in pos.iter("jobDescription")]
            jobs.append(RawJob(
                company=company.name,
                title=title,
                apply_url=f"{base}/job/{job_id}",
                listing_url=f"{base}/job/{job_id}",
                location=clean_ws(pos.findtext("office")),
                description=strip_html(" ".join(d for d in descs if d)),
                posted_at=parse_iso(pos.findtext("createdAt")),
                source_ats=ATSType.PERSONIO,
                employment_type=clean_ws(pos.findtext("employmentType")),
                workplace_type=clean_ws(pos.findtext("schedule")),
                department=clean_ws(pos.findtext("department")),
                job_id=job_id,
            ))
        return jobs
