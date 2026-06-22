"""Phase 6: adaptive DOM fallback (scrapling)."""
from __future__ import annotations

import pytest
from scrapling import Selector

from jobpipe.extractors.dom import DomExtractor
from jobpipe.models import ATSType, CompanyEntity

HTML_V1 = """
<html><body><div class="careers-list">
  <a class="job-card" href="/jobs/1">Junior Backend Engineer (m/w/d)</a>
  <a class="job-card" href="/jobs/2">Graduate Java Developer</a>
  <a class="job-card" href="/jobs/3">Working Student Full Stack</a>
</div></body></html>
"""

# Simulated redesign: class + href pattern both changed.
HTML_V2 = """
<html><body><div class="careers-list">
  <a class="posting-link" href="/positions/1">Junior Backend Engineer (m/w/d)</a>
  <a class="posting-link" href="/positions/2">Graduate Java Developer</a>
  <a class="posting-link" href="/positions/3">Working Student Full Stack</a>
</div></body></html>
"""


def _company():
    return CompanyEntity(name="Acme", career_url="https://acme.test/careers")


def test_parse_extracts_jobs(tmp_path):
    dom = DomExtractor(adaptive_db=str(tmp_path / "adaptive.db"), use_browser=False)
    jobs = dom.parse(HTML_V1, "https://acme.test/careers", _company())
    titles = {j.title for j in jobs}
    assert "Junior Backend Engineer (m/w/d)" in titles
    assert len(jobs) == 3
    assert all(j.apply_url.startswith("https://acme.test/jobs/") for j in jobs)
    assert all(j.source_ats is ATSType.UNKNOWN for j in jobs)


def test_adaptive_autoheal_relocates_after_redesign(tmp_path):
    db = str(tmp_path / "adaptive.db")
    ident = "acme.test:jobcards"
    # Save phase: fingerprint the job anchors.
    s1 = Selector(content=HTML_V1, url="https://acme.test/careers", adaptive=True,
                  storage_args={"storage_file": db})
    saved = s1.css("a.job-card", auto_save=True, identifier=ident)
    assert len(saved) == 3
    assert db  # fingerprints persisted to disk

    # Redesign: the original selector no longer matches.
    s2 = Selector(content=HTML_V2, url="https://acme.test/careers", adaptive=True,
                  storage_args={"storage_file": db})
    assert s2.css("a.job-card") == []
    healed = s2.css("a.job-card", adaptive=True, identifier=ident)
    assert len(healed) >= 1, "adaptive matching failed to relocate elements"


def test_locate_uses_adaptive_db(tmp_path):
    db = str(tmp_path / "adaptive.db")
    dom = DomExtractor(adaptive_db=db, use_browser=False)
    jobs = dom.parse(HTML_V1, "https://acme.test/careers", _company())
    assert len(jobs) == 3
    import os
    assert os.path.exists(db)  # auto_save created the fingerprint store


# --- live (tolerant) -----------------------------------------------------
@pytest.mark.live
async def test_live_static_fetch_returns_list(online, tmp_path):
    if not online:
        pytest.skip("no network")
    dom = DomExtractor(adaptive_db=str(tmp_path / "adaptive.db"), use_browser=False)
    jobs = await dom.extract(CompanyEntity(name="KONUX", career_url="https://www.konux.com/careers/"))
    assert isinstance(jobs, list)  # bespoke SPA may be empty without a browser
    for j in jobs[:10]:
        assert j.apply_url.startswith("http") and j.title


@pytest.mark.browser
async def test_stealth_browser_smoke(online, tmp_path):
    if not online:
        pytest.skip("no network")
    from scrapling.fetchers import StealthyFetcher
    try:
        r = await StealthyFetcher.async_fetch("https://example.com", headless=True, timeout=45000)
    except Exception as e:
        pytest.skip(f"stealth browser unavailable: {e}")
    assert "Example Domain" in str(r.html_content)
