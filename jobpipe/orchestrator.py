"""The harness: classify -> extract -> filter -> dedup -> sink, per company.

Async with split HTTP/browser concurrency budgets and per-domain throttling.
Each company is isolated (one failure never crashes the run) and checkpointed so
a crashed run resumes. Extraction only — nothing is ever submitted/applied.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .classify import classify_url, probe_url
from .config import Settings
from .dedup import Deduper
from .extractors import SUPPORTED_ATS, get_extractor
from .extractors.dom import DomExtractor
from .extractors.workday import WorkdayExtractor
from .filtering.semantic import SemanticMatcher
from .filtering.temporal import passes_window, resolve_posted_at
from .models import ATSType, CompanyEntity, NormalizedJob, utcnow
from .net import ConcurrencyBudget, PerDomainThrottle, ThrottledClient, build_client
from .sink import JobSink

log = logging.getLogger("jobpipe")


@dataclass
class RunStats:
    companies: int = 0
    processed: int = 0
    errors: int = 0
    raw_jobs: int = 0
    matched: int = 0
    written: int = 0
    by_ats: Counter = field(default_factory=Counter)

    def summary(self) -> str:
        top = ", ".join(f"{k}={v}" for k, v in self.by_ats.most_common(8))
        return (f"companies={self.companies} processed={self.processed} errors={self.errors} "
                f"raw={self.raw_jobs} matched={self.matched} written={self.written} | ats: {top}")


class Checkpoint:
    """Records processed company URLs so a crashed run can resume."""

    def __init__(self, db_path: str | Path):
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS processed_companies (url TEXT PRIMARY KEY, ts TEXT)")
        self.conn.commit()

    def done(self, url: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM processed_companies WHERE url = ?", (url,)
        ).fetchone() is not None

    def mark(self, url: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO processed_companies (url, ts) VALUES (?, ?)",
            (url, utcnow().isoformat()),
        )
        self.conn.commit()

    def clear(self) -> None:
        self.conn.execute("DELETE FROM processed_companies")
        self.conn.commit()


class Orchestrator:
    def __init__(self, settings: Settings, *, matcher: SemanticMatcher, deduper: Deduper,
                 sink: JobSink, checkpoint: Checkpoint | None = None, use_browser: bool = True,
                 probe_unknown: bool = True, keep_undated: bool = False, resume: bool = False):
        self.settings = settings
        self.matcher = matcher
        self.deduper = deduper
        self.sink = sink
        self.checkpoint = checkpoint
        self.use_browser = use_browser
        self.probe_unknown = probe_unknown
        self.keep_undated = keep_undated
        self.resume = resume
        self.throttle = PerDomainThrottle(settings.per_domain_delay)
        self.budget = ConcurrencyBudget(settings.http_concurrency, settings.browser_concurrency)
        self.now = utcnow()
        self.stats = RunStats()

    async def run(self, companies: Iterable[CompanyEntity]) -> RunStats:
        companies = list(companies)
        self.stats.companies = len(companies)
        raw_client = build_client(timeout=self.settings.request_timeout)
        client = ThrottledClient(raw_client, throttle=self.throttle, retries=2,
                                 user_agents=self.settings.user_agents)
        dom = DomExtractor(adaptive_db=str(self.settings.adaptive_db), use_browser=self.use_browser,
                           browser_semaphore=self.budget.browser, timeout=self.settings.request_timeout)
        try:
            await asyncio.gather(*(self._process(c, client, dom) for c in companies))
        finally:
            await client.aclose()
        log.info("run complete: %s", self.stats.summary())
        return self.stats

    async def _process(self, company: CompanyEntity, client: ThrottledClient, dom: DomExtractor) -> None:
        if self.resume and self.checkpoint and self.checkpoint.done(company.career_url):
            return
        raws = []
        try:
            async with self.budget.http:
                await self._ensure_ats(company)
                raws = await self._extract(company, client, dom)
        except Exception as e:  # isolate: one company's failure never stops the run
            self.stats.errors += 1
            log.warning("extraction failed for %s (%s): %s", company.name, company.career_url, e)
        self.stats.raw_jobs += len(raws)
        self.stats.by_ats[company.ats.value] += 1
        for raw in raws:
            self._consume(raw)
        self.stats.processed += 1
        if self.checkpoint:
            self.checkpoint.mark(company.career_url)

    async def _ensure_ats(self, company: CompanyEntity) -> None:
        ats, meta = classify_url(company.career_url)
        if ats is ATSType.UNKNOWN and self.probe_unknown:
            ats, meta = await probe_url(company.career_url, timeout=self.settings.request_timeout)
        company.ats = ats
        company.ats_meta = {**(company.ats_meta or {}), **meta}

    async def _extract(self, company: CompanyEntity, client: ThrottledClient, dom: DomExtractor):
        if company.ats in SUPPORTED_ATS:
            if company.ats is ATSType.WORKDAY:
                ex = WorkdayExtractor(client, delay=0.0, max_jobs=self.settings.workday_max_jobs)
            else:
                ex = get_extractor(company.ats, client)
            return await ex.extract(company)
        return await dom.extract(company)  # UNKNOWN / unsupported -> adaptive DOM

    def _consume(self, raw) -> None:
        match = self.matcher.match(raw.title, raw.description)  # title-driven; rejects most
        if not match:
            return
        posted = resolve_posted_at(raw, self.now)
        if not passes_window(posted, self.settings.window_hours, self.now, keep_undated=self.keep_undated):
            return
        job = NormalizedJob.from_raw(raw, seniority=match.seniority,
                                     matched_tech=match.matched_tech, matched_roles=match.matched_roles)
        job.posted_at = posted
        self.stats.matched += 1
        if self.deduper.is_new(job):
            self.sink.append([job])
            self.stats.written += 1
