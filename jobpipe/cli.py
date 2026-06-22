"""Command-line interface. Extraction only — no apply/submit path anywhere.

    python -m jobpipe run --seed data/seed_companies.csv --limit 20 --out data/output/jobs.xlsx
    python -m jobpipe run --all                       # ignore freshness window
    python -m jobpipe classify <career-url>
    python -m jobpipe extract-one <career-url> [--name NAME]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from .classify import classify_url, probe_url
from .config import Settings, get_settings
from .dedup import Deduper
from .discovery import CsvSeedDiscovery
from .extractors import SUPPORTED_ATS, get_extractor
from .extractors.dom import DomExtractor
from .extractors.workday import WorkdayExtractor
from .filtering.semantic import SemanticMatcher
from .models import ATSType, CompanyEntity
from .net import ThrottledClient, build_client
from .orchestrator import Checkpoint, Orchestrator
from .sink import JobSink

REPO_DIR = Path(__file__).resolve().parent.parent


def _resolve(path: str | Path) -> Path:
    """Resolve a config/data path relative to cwd, falling back to the repo root."""
    p = Path(path)
    if p.exists():
        return p
    alt = REPO_DIR / p
    return alt if alt.exists() else p


def _settings_for_run(args) -> Settings:
    s = get_settings()
    updates: dict = {}
    if getattr(args, "all", False):
        updates["window_hours"] = 0
    elif getattr(args, "window_hours", None) is not None:
        updates["window_hours"] = args.window_hours
    if getattr(args, "require_seniority", False):
        updates["require_seniority"] = True
    if getattr(args, "concurrency", None):
        updates["http_concurrency"] = args.concurrency
    if getattr(args, "seed", None):
        updates["seed_csv"] = Path(args.seed)
    if getattr(args, "out", None):
        updates["output_xlsx"] = Path(args.out)
    return s.model_copy(update=updates)


async def _cmd_run(args) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = _settings_for_run(args)
    companies = list(CsvSeedDiscovery(_resolve(settings.seed_csv), limit=args.limit))
    matcher = SemanticMatcher(_resolve(settings.keywords), require_seniority=settings.require_seniority)
    deduper = Deduper(settings.state_db)
    sink = JobSink(settings.output_xlsx.with_suffix(".csv"), settings.output_xlsx, reset=not args.resume)
    checkpoint = Checkpoint(settings.state_db)
    if args.fresh:
        checkpoint.clear()

    win = "ALL (no window)" if settings.window_hours == 0 else f"{settings.window_hours}h"
    print(f"Extracting {len(companies)} companies | window={win} | "
          f"strict_seniority={settings.require_seniority} | browser={not args.no_browser}")
    orch = Orchestrator(settings, matcher=matcher, deduper=deduper, sink=sink, checkpoint=checkpoint,
                        use_browser=not args.no_browser, keep_undated=args.keep_undated, resume=args.resume)
    stats = await orch.run(companies)
    out = sink.finalize()
    deduper.close()
    print(f"\n✔ {stats.summary()}")
    print(f"✔ wrote {stats.written} new job(s) -> {out}")
    return 0


async def _cmd_classify(args) -> int:
    ats, meta = classify_url(args.url)
    if ats is ATSType.UNKNOWN and not args.no_probe:
        ats, meta = await probe_url(args.url)
    print(f"{ats.value}\t{meta}")
    return 0


async def _cmd_extract_one(args) -> int:
    ats, meta = classify_url(args.url)
    if ats is ATSType.UNKNOWN:
        ats, meta = await probe_url(args.url)
    company = CompanyEntity(name=args.name or args.url, career_url=args.url, ats=ats, ats_meta=meta)
    matcher = SemanticMatcher(_resolve(get_settings().keywords))
    raw_client = build_client(timeout=30)
    client = ThrottledClient(raw_client)
    try:
        if ats in SUPPORTED_ATS:
            ex = WorkdayExtractor(client, delay=0.0) if ats is ATSType.WORKDAY else get_extractor(ats, client)
        else:
            ex = DomExtractor(adaptive_db=str(get_settings().adaptive_db), use_browser=not args.no_browser)
        jobs = await ex.extract(company)
    finally:
        await client.aclose()
    kept = 0
    print(f"ATS={ats.value} meta={meta} | extracted {len(jobs)} postings")
    for j in jobs:
        m = matcher.match(j.title, j.description)
        if m:
            kept += 1
            print(f"  KEEP [{m.seniority:14}] {', '.join(m.matched_tech)[:24]:24} | {j.title[:55]}")
    print(f"-> {kept} match the tech/seniority filter (role-level; window not applied)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="jobpipe",
                                description="Extract German entry/junior/mid/graduate tech jobs (extraction only).")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the full extraction pipeline")
    r.add_argument("--seed", help="seed CSV path (default: config)")
    r.add_argument("--limit", type=int, help="only the first N companies")
    r.add_argument("--window-hours", type=int, dest="window_hours", help="freshness window (default 48)")
    r.add_argument("--all", action="store_true", help="ignore freshness window (extract all)")
    r.add_argument("--require-seniority", action="store_true", help="strict: require junior/entry/mid/grad token")
    r.add_argument("--out", help="output .xlsx path")
    r.add_argument("--concurrency", type=int, help="max concurrent HTTP requests")
    r.add_argument("--no-browser", action="store_true", help="disable stealth-browser DOM fallback")
    r.add_argument("--keep-undated", action="store_true", help="keep postings with no parseable date")
    r.add_argument("--resume", action="store_true", help="skip companies already processed (checkpoint)")
    r.add_argument("--fresh", action="store_true", help="clear the resume checkpoint before running")

    c = sub.add_parser("classify", help="show the detected ATS for a career URL")
    c.add_argument("url")
    c.add_argument("--no-probe", action="store_true", help="URL pattern only; skip live probe")

    e = sub.add_parser("extract-one", help="extract+filter a single career URL (debug)")
    e.add_argument("url")
    e.add_argument("--name", help="company name label")
    e.add_argument("--no-browser", action="store_true")

    args = p.parse_args(argv)
    handler = {"run": _cmd_run, "classify": _cmd_classify, "extract-one": _cmd_extract_one}[args.cmd]
    return asyncio.run(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
