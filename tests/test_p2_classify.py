"""Phase 2: ATS classification."""
from __future__ import annotations

import csv

import pytest

from jobpipe.classify import classify_url, probe_url
from jobpipe.models import ATSType
from tests.conftest import REPO_ROOT


@pytest.mark.parametrize("url,ats,meta_subset", [
    ("https://acme.wd3.myworkdayjobs.com/en-US/External", ATSType.WORKDAY,
     {"tenant": "acme", "shard": "wd3", "site": "External"}),
    ("https://acme.wd1.myworkdaysite.com/Careers", ATSType.WORKDAY,
     {"tenant": "acme", "shard": "wd1", "site": "Careers"}),
    ("https://api.lever.co/v0/postings/netflix?mode=json", ATSType.LEVER, {"client": "netflix"}),
    ("https://jobs.lever.co/spotify", ATSType.LEVER, {"client": "spotify"}),
    ("https://boards.greenhouse.io/airbnb", ATSType.GREENHOUSE, {"token": "airbnb"}),
    ("https://boards-api.greenhouse.io/v1/boards/boku/jobs?content=true", ATSType.GREENHOUSE, {"token": "boku"}),
    ("https://boards.greenhouse.io/embed/job_board/js?for=atolls", ATSType.GREENHOUSE, {"token": "atolls"}),
    ("https://job-boards.eu.greenhouse.io/raisin", ATSType.GREENHOUSE, {"token": "raisin"}),
    ("https://api.ashbyhq.com/posting-api/job-board/Payrails?includeCompensation=true", ATSType.ASHBY, {"org": "Payrails"}),
    ("https://api.smartrecruiters.com/v1/companies/EnpalBV/postings?limit=5", ATSType.SMARTRECRUITERS, {"company": "EnpalBV"}),
    ("https://join.smartrecruiters.com/Brainlab/abc-uuid", ATSType.SMARTRECRUITERS, {"company": "Brainlab"}),
    ("https://holidaycheck.jobs.personio.de/?language=en", ATSType.PERSONIO, {"subdomain": "holidaycheck"}),
    ("https://acme.jobs.personio.com/xml", ATSType.PERSONIO, {"subdomain": "acme"}),
    ("https://jobs.ashbyhq.com/openai", ATSType.ASHBY, {"org": "openai"}),
    ("https://careers.smartrecruiters.com/Bosch", ATSType.SMARTRECRUITERS, {"company": "Bosch"}),
    ("https://acme.recruitee.com/", ATSType.RECRUITEE, {"company": "acme"}),
    ("https://fleetster.breezy.hr/", ATSType.BREEZY, {"subdomain": "fleetster"}),
    ("https://apply.workable.com/tado/", ATSType.WORKABLE, {"account": "tado"}),
    ("https://om-digitalsolutions.career.softgarden.de/", ATSType.SOFTGARDEN, {}),
    ("https://career5.successfactors.eu/career", ATSType.SUCCESSFACTORS, {}),
    ("https://example.jobs2web.com/", ATSType.SUCCESSFACTORS, {}),
    ("https://join.com/api/public/companies/123/jobs", ATSType.JOIN, {}),
    ("https://www.celonis.com/careers/jobs/", ATSType.UNKNOWN, {}),
])
def test_classify_url_patterns(url, ats, meta_subset):
    got_ats, got_meta = classify_url(url)
    assert got_ats is ats
    for k, v in meta_subset.items():
        assert got_meta.get(k) == v


def test_personio_company_marketing_site_is_not_personio_board():
    # personio.com/about-personio/careers is Personio's own marketing page, not a feed host
    ats, _ = classify_url("https://www.personio.com/about-personio/careers/")
    assert ats is ATSType.UNKNOWN


def _seed_rows():
    with (REPO_ROOT / "data" / "seed_companies.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_classify_handles_every_seed_url_without_error():
    rows = _seed_rows()
    for r in rows:
        ats, meta = classify_url(r["career_url"])
        assert isinstance(ats, ATSType)
        assert isinstance(meta, dict)


def test_seed_known_ats_hosts_detected():
    by_company = {r["company"]: r["career_url"] for r in _seed_rows()}
    assert classify_url(by_company["HolidayCheck"])[0] is ATSType.PERSONIO
    assert classify_url(by_company["Fleetster"])[0] is ATSType.BREEZY
    assert classify_url(by_company["OM Digital Solutions"])[0] is ATSType.SOFTGARDEN


# --- live probe (tolerant) ----------------------------------------------
@pytest.mark.live
async def test_probe_url_live_personio(online):
    if not online:
        pytest.skip("no network")
    ats, _ = await probe_url("https://holidaycheck.jobs.personio.de/?language=en")
    # Reachable -> PERSONIO; transient network failure -> UNKNOWN (tolerated).
    assert ats in (ATSType.PERSONIO, ATSType.UNKNOWN)
