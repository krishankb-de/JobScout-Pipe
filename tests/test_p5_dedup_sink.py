"""Phase 5: dedup + Excel sink."""
from __future__ import annotations

import pandas as pd

from jobpipe.dedup import Deduper
from jobpipe.models import OUTPUT_COLUMNS, ATSType, NormalizedJob
from jobpipe.sink import JobSink


def _job(url, title="Junior Backend Engineer", company="Foo"):
    return NormalizedJob(company=company, title=title, apply_url=url,
                         source_ats=ATSType.LEVER, seniority="Junior",
                         matched_tech=["Python", "Backend"], location="Berlin")


# --- dedup ---------------------------------------------------------------
def test_is_new_then_duplicate():
    d = Deduper(":memory:")
    j = _job("https://x.co/jobs/1")
    assert d.is_new(j) is True
    assert d.is_new(j) is False
    assert d.seen(j) is True
    assert d.count() == 1


def test_trailing_slash_is_same_job():
    d = Deduper(":memory:")
    assert d.is_new(_job("https://x.co/jobs/1")) is True
    assert d.is_new(_job("https://x.co/jobs/1/")) is False  # canonicalized


def test_dedup_persists_across_runs(tmp_path):
    db = tmp_path / "state.sqlite"
    with Deduper(db) as d1:
        assert d1.is_new(_job("https://x.co/a")) is True
        assert d1.is_new(_job("https://x.co/b")) is True
    # New process/run: same jobs are no longer new.
    with Deduper(db) as d2:
        assert d2.count() == 2
        assert d2.is_new(_job("https://x.co/a")) is False
        assert d2.is_new(_job("https://x.co/b")) is False
        assert d2.is_new(_job("https://x.co/c")) is True


# --- sink ----------------------------------------------------------------
def test_sink_writes_xlsx_with_exact_columns(tmp_path):
    sink = JobSink(tmp_path / "jobs.csv", tmp_path / "jobs.xlsx")
    sink.append([_job("https://x.co/1"), _job("https://x.co/2", title="Graduate Java Developer")])
    out = sink.finalize()
    assert out.exists() and (tmp_path / "jobs.csv").exists()
    df = pd.read_excel(out)
    assert list(df.columns) == OUTPUT_COLUMNS
    assert len(df) == 2
    assert df.iloc[0]["Matched Tech Stack"] == "Python, Backend"
    assert df.iloc[0]["Source ATS"] == "lever"


def test_sink_empty_produces_headers_only(tmp_path):
    sink = JobSink(tmp_path / "e.csv", tmp_path / "e.xlsx")
    out = sink.finalize()
    df = pd.read_excel(out)
    assert list(df.columns) == OUTPUT_COLUMNS
    assert len(df) == 0


def test_sink_incremental_appends_accumulate(tmp_path):
    sink = JobSink(tmp_path / "j.csv", tmp_path / "j.xlsx")
    sink.append([_job("https://x.co/1")])
    sink.append([_job("https://x.co/2"), _job("https://x.co/3")])
    assert sink.written == 3
    df = pd.read_excel(sink.finalize())
    assert len(df) == 3
