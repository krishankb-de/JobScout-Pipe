"""Phase 1: models + config."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from jobpipe.config import Settings, get_settings
from jobpipe.models import (
    OUTPUT_COLUMNS,
    ATSType,
    CompanyEntity,
    NormalizedJob,
    RawJob,
    canonical_url,
)


# --- ATSType -------------------------------------------------------------
def test_native_extractor_flag():
    for ats in (ATSType.LEVER, ATSType.PERSONIO, ATSType.WORKDAY,
                ATSType.SUCCESSFACTORS, ATSType.JOIN):
        assert ats.has_native_extractor
    assert not ATSType.UNKNOWN.has_native_extractor
    assert not ATSType.GREENHOUSE.has_native_extractor


# --- canonical_url -------------------------------------------------------
@pytest.mark.parametrize("a,b", [
    ("https://x.co/jobs/", "https://x.co/jobs"),
    ("https://x.co/jobs#apply", "https://x.co/jobs"),
    ("https://x.co/jobs/#x", "https://x.co/jobs"),
])
def test_canonical_url_normalizes(a, b):
    assert canonical_url(a) == b


# --- CompanyEntity -------------------------------------------------------
def test_company_entity_requires_http():
    c = CompanyEntity(name="Foo", career_url="https://foo.de/careers")
    assert c.ats is ATSType.UNKNOWN and c.country == "DE"
    with pytest.raises(ValidationError):
        CompanyEntity(name="Bad", career_url="foo.de/careers")


# --- NormalizedJob -------------------------------------------------------
def _job(**kw):
    base = dict(company="Foo", title="Junior Backend Engineer",
                apply_url="https://foo.de/jobs/1", source_ats=ATSType.LEVER,
                seniority="Junior", matched_tech=["Python", "Backend"])
    base.update(kw)
    return NormalizedJob(**base)


def test_to_row_has_exact_columns_in_order():
    row = _job().to_row()
    assert list(row.keys()) == OUTPUT_COLUMNS
    assert row["Matched Tech Stack"] == "Python, Backend"
    assert row["Source ATS"] == "lever"
    # Timestamp is ISO 8601
    datetime.fromisoformat(row["Timestamp"])


def test_dedup_key_depends_on_canonical_url():
    a = _job(apply_url="https://foo.de/jobs/1")
    b = _job(apply_url="https://foo.de/jobs/1/")  # trailing slash -> same key
    c = _job(apply_url="https://foo.de/jobs/2")
    assert a.dedup_key() == b.dedup_key()
    assert a.dedup_key() != c.dedup_key()


def test_from_raw_maps_fields():
    raw = RawJob(company="Foo", title="Graduate Software Engineer",
                 apply_url="https://foo.de/jobs/9", location="Berlin",
                 source_ats=ATSType.PERSONIO,
                 posted_at=datetime(2026, 6, 11, tzinfo=timezone.utc))
    n = NormalizedJob.from_raw(raw, seniority="Graduate", matched_tech=["Java"])
    assert n.company == "Foo" and n.location == "Berlin"
    assert n.source_ats is ATSType.PERSONIO
    assert n.to_row()["Seniority Level"] == "Graduate"


# --- Settings ------------------------------------------------------------
def test_settings_defaults():
    s = get_settings()
    assert s.window_hours == 48 and s.require_seniority is False
    assert s.keep_all is False


def test_window_hours_zero_means_keep_all():
    assert Settings(window_hours=0).keep_all is True


def test_negative_window_rejected():
    with pytest.raises(ValidationError):
        Settings(window_hours=-1)


def test_browser_concurrency_clamped_to_10():
    assert Settings(browser_concurrency=50).browser_concurrency == 10
    assert Settings(browser_concurrency=0).browser_concurrency == 1


def test_proxy_urls_comma_split():
    s = Settings(proxy_urls="http://a:1, http://b:2 ,")
    assert s.proxy_urls == ["http://a:1", "http://b:2"]
