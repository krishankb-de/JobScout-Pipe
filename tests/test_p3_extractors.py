"""Phase 3: API-first extractors (live)."""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from jobpipe.extractors import (
    REGISTRY,
    SUPPORTED_ATS,
    AshbyExtractor,
    GreenhouseExtractor,
    JoinExtractor,
    LeverExtractor,
    PersonioExtractor,
    SmartRecruitersExtractor,
    SuccessFactorsExtractor,
    WorkdayExtractor,
    get_extractor,
)
from jobpipe.models import ATSType, CompanyEntity

pytestmark = pytest.mark.live


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as c:
        yield c


def _company(name, url, **meta):
    return CompanyEntity(name=name, career_url=url, ats_meta=meta or {})


async def _run_or_skip(extractor, company):
    try:
        return await extractor.extract(company)
    except httpx.TransportError as e:
        pytest.skip(f"network unavailable: {e}")


def _assert_valid(jobs, ats):
    assert isinstance(jobs, list)
    for j in jobs[:50]:
        assert j.title.strip()
        assert j.apply_url.startswith("http")
        assert j.source_ats is ats


# --- registry (offline) --------------------------------------------------
@pytest.mark.parametrize("ats,cls", [
    (ATSType.LEVER, LeverExtractor),
    (ATSType.PERSONIO, PersonioExtractor),
    (ATSType.WORKDAY, WorkdayExtractor),
    (ATSType.SUCCESSFACTORS, SuccessFactorsExtractor),
    (ATSType.JOIN, JoinExtractor),
])
def test_registry_covers_mandated_ats(ats, cls):
    assert REGISTRY[ats] is cls
    assert ats in SUPPORTED_ATS


def test_get_extractor_unknown_is_none():
    assert get_extractor(ATSType.UNKNOWN, client=None) is None


# --- live extractors -----------------------------------------------------
async def test_lever_live(online, client):
    if not online:
        pytest.skip("no network")
    jobs = await _run_or_skip(LeverExtractor(client), _company("LeverDemo", "https://jobs.lever.co/leverdemo"))
    assert len(jobs) > 0
    _assert_valid(jobs, ATSType.LEVER)
    assert any(j.posted_at for j in jobs)


async def test_personio_live(online, client):
    if not online:
        pytest.skip("no network")
    jobs = await _run_or_skip(PersonioExtractor(client), _company("Building Radar", "https://building-radar.jobs.personio.de/"))
    assert len(jobs) > 0
    _assert_valid(jobs, ATSType.PERSONIO)
    assert any(j.posted_at for j in jobs)  # Personio feed carries createdAt
    assert all("/job/" in j.apply_url for j in jobs[:10])


async def test_greenhouse_live(online, client):
    if not online:
        pytest.skip("no network")
    jobs = await _run_or_skip(GreenhouseExtractor(client), _company("Boku", "https://boards.greenhouse.io/boku"))
    assert len(jobs) > 0
    _assert_valid(jobs, ATSType.GREENHOUSE)


async def test_ashby_live(online, client):
    if not online:
        pytest.skip("no network")
    jobs = await _run_or_skip(AshbyExtractor(client), _company("DeepL", "https://jobs.ashbyhq.com/DeepL"))
    assert len(jobs) > 0
    _assert_valid(jobs, ATSType.ASHBY)


async def test_smartrecruiters_live(online, client):
    if not online:
        pytest.skip("no network")
    jobs = await _run_or_skip(SmartRecruitersExtractor(client), _company("Brainlab", "https://careers.smartrecruiters.com/Brainlab"))
    assert len(jobs) > 0
    _assert_valid(jobs, ATSType.SMARTRECRUITERS)


async def test_workday_live(online, client):
    if not online:
        pytest.skip("no network")
    ex = WorkdayExtractor(client, delay=0.3, max_jobs=60)
    jobs = await _run_or_skip(ex, _company("KION Group", "https://kiongroup.wd3.myworkdayjobs.com/en-US/KIONGroup"))
    assert len(jobs) > 0
    _assert_valid(jobs, ATSType.WORKDAY)
    assert all("myworkdayjobs.com" in j.apply_url for j in jobs[:10])
    assert any(j.posted_at_text for j in jobs)  # relative "Posted X Days Ago"


async def test_join_live_with_company_id(online, client):
    if not online:
        pytest.skip("no network")
    jobs = await _run_or_skip(JoinExtractor(client), _company("JoinCo", "https://join.com/", company_id=1000))
    _assert_valid(jobs, ATSType.JOIN)  # tolerant: may be empty if board cleared


async def test_join_without_id_returns_empty(client):
    jobs = await JoinExtractor(client).extract(_company("NoId", "https://join.com/"))
    assert jobs == []


async def test_successfactors_tolerant(online, client):
    if not online:
        pytest.skip("no network")
    # Legacy SF portals usually lack the v1 API -> graceful empty, no exception.
    jobs = await _run_or_skip(
        SuccessFactorsExtractor(client),
        _company("MANN+HUMMEL", "https://career5.successfactors.eu/career?career_company=mannhummel"),
    )
    assert isinstance(jobs, list)
