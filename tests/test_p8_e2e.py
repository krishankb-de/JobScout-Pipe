"""Phase 8: orchestrator harness + CLI end-to-end (live)."""
from __future__ import annotations

import pandas as pd
import pytest

from jobpipe.cli import main
from jobpipe.config import Settings, get_settings
from jobpipe.dedup import Deduper
from jobpipe.models import OUTPUT_COLUMNS, CompanyEntity
from jobpipe.orchestrator import Orchestrator
from jobpipe.sink import JobSink
from tests.conftest import REPO_ROOT

KW = REPO_ROOT / "config" / "keywords.yaml"
ALLOWED_SENIORITY = {"Junior", "Entry Level", "Mid Level", "Graduate", "Working Student",
                     "Intern", "Trainee", "Associate", "Dual Study", "Unspecified"}

# ATS-direct fixtures (classify without a probe) that reliably hold tech roles.
YIELD_COMPANIES = [
    CompanyEntity(name="Building Radar", career_url="https://building-radar.jobs.personio.de/"),
    CompanyEntity(name="Contentful", career_url="https://boards.greenhouse.io/contentful"),
    CompanyEntity(name="Giant Swarm", career_url="https://giant-swarm.jobs.personio.de/"),
]


def _settings(tmp_path, **over) -> Settings:
    base = dict(window_hours=0, per_domain_delay=0.0, http_concurrency=10,
                keywords=KW, state_db=tmp_path / "state.sqlite",
                adaptive_db=tmp_path / "adaptive.sqlite", output_xlsx=tmp_path / "jobs.xlsx")
    base.update(over)
    return Settings(**base)


def _orch(settings, deduper, sink, **kw):
    from jobpipe.filtering.semantic import SemanticMatcher
    return Orchestrator(settings, matcher=SemanticMatcher(KW), deduper=deduper, sink=sink,
                        use_browser=False, probe_unknown=False, **kw)


@pytest.mark.live
async def test_pipeline_yields_matches(online, tmp_path):
    if not online:
        pytest.skip("no network")
    s = _settings(tmp_path)
    deduper = Deduper(s.state_db)
    sink = JobSink(tmp_path / "jobs.csv", s.output_xlsx)
    stats = await _orch(s, deduper, sink).run(YIELD_COMPANIES)
    out = sink.finalize()
    assert stats.matched > 0 and stats.written > 0
    df = pd.read_excel(out)
    assert list(df.columns) == OUTPUT_COLUMNS
    assert len(df) > 0
    assert df["Direct Apply URL"].str.startswith("http").all()
    assert set(df["Seniority Level"]).issubset(ALLOWED_SENIORITY)


@pytest.mark.live
async def test_dedup_across_runs(online, tmp_path):
    if not online:
        pytest.skip("no network")
    s = _settings(tmp_path)
    deduper = Deduper(s.state_db)  # shared across both runs
    run1 = await _orch(s, deduper, JobSink(tmp_path / "r1.csv", tmp_path / "r1.xlsx")).run(YIELD_COMPANIES)
    assert run1.written > 0
    run2 = await _orch(s, deduper, JobSink(tmp_path / "r2.csv", tmp_path / "r2.xlsx")).run(YIELD_COMPANIES)
    assert run2.matched > 0 and run2.written == 0  # already seen -> nothing new


@pytest.mark.live
async def test_error_isolation(online, tmp_path):
    if not online:
        pytest.skip("no network")
    s = _settings(tmp_path)
    sink = JobSink(tmp_path / "j.csv", tmp_path / "j.xlsx")
    companies = [
        CompanyEntity(name="Broken", career_url="https://nonexistent.invalid.test/careers"),
        CompanyEntity(name="Giant Swarm", career_url="https://giant-swarm.jobs.personio.de/"),
    ]
    stats = await _orch(s, Deduper(s.state_db), sink).run(companies)
    assert stats.processed == 2          # the broken company did not stop the run
    assert stats.written > 0             # the good company (tech roles) still produced output


@pytest.mark.live
def test_cli_run_smoke(online, tmp_path, monkeypatch):
    if not online:
        pytest.skip("no network")
    seed = tmp_path / "seed.csv"
    seed.write_text(
        "company,sector,city,career_url,source\n"
        "Building Radar,SaaS,Munich,https://building-radar.jobs.personio.de/,startup\n"
        "Contentful,CMS,Berlin,https://boards.greenhouse.io/contentful,startup\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.xlsx"
    for k, v in {
        "JOBPIPE_SEED_CSV": str(seed), "JOBPIPE_OUTPUT_XLSX": str(out),
        "JOBPIPE_STATE_DB": str(tmp_path / "s.sqlite"), "JOBPIPE_ADAPTIVE_DB": str(tmp_path / "a.sqlite"),
        "JOBPIPE_PER_DOMAIN_DELAY": "0",
    }.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    try:
        rc = main(["run", "--all", "--no-browser"])
        assert rc == 0
        assert out.exists()
        df = pd.read_excel(out)
        assert list(df.columns) == OUTPUT_COLUMNS
        assert len(df) > 0
    finally:
        get_settings.cache_clear()
