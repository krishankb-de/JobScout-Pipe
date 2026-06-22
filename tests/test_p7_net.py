"""Phase 7: net layer + discovery interfaces."""
from __future__ import annotations

import time

import httpx
import pytest

from jobpipe.discovery import (
    CsvSeedDiscovery,
    DiscoveryNotConfigured,
    HandelsregisterDiscovery,
    SerpDiscovery,
)
from jobpipe.models import CompanyEntity
from jobpipe.net import (
    ConcurrencyBudget,
    PerDomainThrottle,
    ProxyRotator,
    ThrottledClient,
    TransientHTTPError,
    build_client,
)
from tests.conftest import REPO_ROOT

SEED = REPO_ROOT / "data" / "seed_companies.csv"


# --- throttle ------------------------------------------------------------
async def test_per_domain_throttle_spaces_same_host():
    t = PerDomainThrottle(min_interval=0.25)
    start = time.monotonic()
    await t.wait("https://a.co/x")
    await t.wait("https://a.co/y")  # must wait ~0.25s
    assert time.monotonic() - start >= 0.24


async def test_throttle_does_not_block_different_hosts():
    t = PerDomainThrottle(min_interval=0.25)
    start = time.monotonic()
    await t.wait("https://a.co/x")
    await t.wait("https://b.co/x")  # first hit per host -> no wait
    assert time.monotonic() - start < 0.1


def test_concurrency_budget_browser_clamped():
    b = ConcurrencyBudget(http=30, browser=50)
    assert b.http._value == 30
    assert b.browser._value == 10  # 8GB RAM ceiling


# --- proxy ---------------------------------------------------------------
def test_proxy_rotator_empty():
    p = ProxyRotator()
    assert not p and p.next() is None


def test_proxy_rotator_round_robin():
    p = ProxyRotator(["http://a:1", "http://b:2"])
    assert bool(p) and len(p) == 2
    assert [p.next() for _ in range(3)] == ["http://a:1", "http://b:2", "http://a:1"]


# --- ThrottledClient retry ----------------------------------------------
class _FakeClient:
    def __init__(self, fail_n=0, status=200):
        self.calls = 0
        self.fail_n = fail_n
        self.status = status

    async def request(self, method, url, **kw):
        self.calls += 1
        if self.calls <= self.fail_n:
            raise httpx.ConnectError("boom")
        return httpx.Response(self.status, request=httpx.Request(method, url))


async def test_retry_recovers_after_transient_errors():
    fake = _FakeClient(fail_n=2)
    tc = ThrottledClient(fake, throttle=None, retries=3)
    resp = await tc.get("https://x.co/1")
    assert resp.status_code == 200 and fake.calls == 3


async def test_retry_gives_up_and_raises():
    fake = _FakeClient(fail_n=99)
    tc = ThrottledClient(fake, throttle=None, retries=2)
    with pytest.raises(httpx.ConnectError):
        await tc.get("https://x.co/1")
    assert fake.calls == 3  # initial + 2 retries


async def test_5xx_treated_as_transient():
    fake = _FakeClient(fail_n=0, status=503)
    tc = ThrottledClient(fake, throttle=None, retries=1)
    with pytest.raises(TransientHTTPError):
        await tc.get("https://x.co/1")
    assert fake.calls == 2


def test_build_client_config():
    c = build_client(timeout=12)
    assert isinstance(c, httpx.AsyncClient)
    assert c.timeout.read == 12


# --- discovery -----------------------------------------------------------
def test_csv_seed_yields_companies():
    rows = list(CsvSeedDiscovery(SEED))
    assert len(rows) >= 250
    assert all(isinstance(c, CompanyEntity) for c in rows)
    assert all(c.career_url.startswith("http") for c in rows)


def test_csv_seed_limit():
    rows = list(CsvSeedDiscovery(SEED, limit=7))
    assert len(rows) == 7


def test_serp_stub_raises_not_configured():
    with pytest.raises(DiscoveryNotConfigured):
        list(SerpDiscovery(["Acme GmbH"]))


def test_handelsregister_stub_raises_not_configured():
    with pytest.raises(DiscoveryNotConfigured):
        list(HandelsregisterDiscovery())
