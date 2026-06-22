# Plan: Automated German Tech-Job Extraction Pipeline

## Context
Greenfield project in `/Users/krish/Desktop/Projects/Job_Listings` (empty, not a git repo). Goal: an
enterprise-style pipeline that discovers German company career pages, detects the ATS, **extracts** matching tech roles,
and writes a precision Excel workbook (incl. the direct apply URL as *data only*). Brief targets 500K companies via
Handelsregister+SERP+residential proxies, but those layers need paid keys we can't run here. User wants the plan stored
in-repo, then **implemented and tested phase-by-phase inside a Python venv**, installing real libs.

### EXTRACTION ONLY (hard constraint)
The pipeline **only extracts and records** job postings. It must **never** auto-apply, autofill forms, submit
applications, log in, or otherwise act on the apply URL — that URL is just a column in the output sheet. Drop all
"apply workflow" framing from the brief (Tsenta autofill/MCP/CLI apply, etc.). No phase builds or invokes application
logic.

### Target roles (expanded, per user)
Capture all of these (and close variants), in **junior / entry / mid-level / graduate** (also associate, intern, working
student, trainee, dual-study) seniority — explicitly **including mid-level**:
- AI/ML engineer, backend engineer, Python engineer/developer, **Java** engineer/developer, full-stack engineer,
  software engineer, backend software engineer, full-stack software engineer, software developer, developer,
  graduate engineer / graduate software engineer / graduate software developer.
Match logic = **lenient**: tech-role match ∧ ¬negative-seniority (senior/lead/principal/staff/director/head/VP/chief).
A plain "Software Engineer" with no seniority token IS included (seniority recorded as "Unspecified"); mid-level is a
positive, NOT a negative. `--require-seniority` flag tightens to strict (must carry junior/entry/mid/grad token).

### Locked decisions (from user)
- **Scope:** Build + live-test the *full extraction pipeline* on the ~350 seed companies the user provided. Discovery
  (Handelsregister/SERP) + proxy rotation = clean documented interfaces w/ working local defaults, left unconfigured.
- **DOM fallback:** Install stealth browser now (`pip install "scrapling[fetchers]"` + `scrapling install`).
- **Tests:** Hit **live** ATS endpoints every run (user override of mocked default). Use stable real tenants; tolerate
  empty results gracefully so a quiet 48h window ≠ test failure.

### Verified facts (research, not assumptions)
- Python 3.13.9 (Anaconda) present. Lever API → 200; Personio XML (`holidaycheck.jobs.personio.de/xml`) → 200, schema
  `<workzag-jobs>/<position>` (id, subcompany, office, department, recruitingCategory, name, jobDescriptions…) and already
  lists a "(Junior) Software Engineer"; Join `api.join.com/v2/jobs` → 422 (exists, needs params).
- **scrapling 0.4.9** (rel. 2026-06-07), Python ≥3.10. Base deps light (lxml, orjson, cssselect, tld, w3lib); browsers
  via separate `scrapling install`. **API corrections vs brief:** adaptive param is `adaptive=True` (+ `auto_save=True`),
  NOT `auto_match`; fetchers = `Fetcher`/`AsyncFetcher`/`StealthyFetcher`/`DynamicFetcher`; real Scrapy-like `Spider`
  with `crawldir` checkpoints + `stream()`; `find_similar()` for relocation.

## Project structure
```
Job_Listings/
├── PLAN.md  README.md  pyproject.toml  requirements.txt  .env.example  .gitignore
├── data/seed_companies.csv          # built from user's 3 lists
├── data/output/                     # generated csv/xlsx (+ state.sqlite, adaptive.sqlite)
├── config/keywords.yaml             # tech / seniority / negative dicts
├── scripts/build_seed_csv.py        # parse provided lists -> seed_companies.csv
├── jobpipe/
│   ├── config.py models.py classify.py normalize.py dedup.py sink.py orchestrator.py cli.py
│   ├── extractors/{base,lever,personio,workday,successfactors,join,dom}.py
│   ├── filtering/{semantic,temporal}.py
│   ├── discovery/{base,csv_seed,serp,handelsregister}.py
│   └── net/{http,proxy,throttle}.py
└── tests/{conftest,test_classify,test_extractors_*,test_filtering,test_dedup,test_sink,test_dom,test_net,test_end_to_end}.py
```

## Phases (implement → install deps → test in venv, after each)
Each phase ends with `source .venv/bin/activate && pytest tests/test_<phase>.py -q` (live where noted) before moving on.

**P0 — Scaffold + venv + seed data.** `python3 -m venv .venv`; requirements/pyproject; `.gitignore` (.venv, data/output,
*.sqlite); `.env.example`. `scripts/build_seed_csv.py` parses the 3 provided lists → `data/seed_companies.csv`
(cols: company, sector, city, career_url), cleaning malformed URLs (strip wrapping `()`, trailing `/`). Copy this plan to
repo `PLAN.md`. *Test:* package imports; seed CSV row count > 300 and all URLs valid http(s).

**P1 — Models + config.** Pydantic v2: `ATSType` enum (lever/personio/workday/successfactors/join/greenhouse/unknown),
`CompanyEntity`, `RawJob`, `NormalizedJob` (8 output cols + provenance/posted_at). `config.py` via pydantic-settings/.env
(window_hours=48, concurrency budgets, paths, optional SERP/proxy keys). *Test:* validation + bad-input rejection.

**P2 — ATS classification.** `classify.py`: domain/URL regex → `ATSType` (`*.jobs.personio.de`→personio incl .com/.de;
`api.lever.co`/`jobs.lever.co`→lever; `*.myworkdayjobs.com|myworkdaysite.com` + tenant/shard/site regex→workday;
`join.com`→join; jobs2web/successfactors→successfactors). Optional async HTTP probe to refine `unknown`. *Test (live+unit):*
classify every seed URL; assert known mappings; probe a few.

**P3 — API-first extractors (core).** Each: `async extract(company)->list[NormalizedJob]` via `normalize.py`.
- *lever:* GET `api.lever.co/v0/postings/{client}?mode=json`; map hostedUrl/applyUrl/categories/workplaceType/createdAt(ms).
- *personio:* GET `{sub}.jobs.personio.de/xml?language=en`; lxml parse `<position>`; iterate locales en/de.
- *join:* discover integer company_id → `join.com/api/public/companies/{id}/jobs` (page/pageSize≤100, pagination obj).
- *workday:* `/{tenant}/siteMap.xml` (capital S) → POST `/wday/cxs/{tenant}/{site}/jobs` {appliedFacets,limit,offset};
  facet-fragment to stay <2000 cap; 1.5–2.0s delay; GET job detail for HTML; parse relative `postedOn`.
- *successfactors:* capture `x-csrf-token`, POST `/services/recruiting/v1/jobs` {locale,paging}; iterate locales
  (en_US,de_DE); secondary GET for description; tolerate CAPTCHA (skip+log). *Test (live):* Lever+Personio return
  postings with required fields; others assert reachable/parse, empty-tolerant.

**P4 — Semantic + temporal filtering.** `semantic.py`: FlashText `KeywordProcessor` from `keywords.yaml`:
- *tech dict:* ai/ml engineer, backend (engineer/developer), python (engineer/developer), **java** (engineer/developer),
  full-stack/fullstack (engineer/developer), software engineer, software developer, web developer, developer, + DE terms
  (softwareentwickler, entwickler, softwareingenieur).
- *seniority dict (positive):* junior, entry/entry-level, **mid/mid-level/intermediate**, graduate/grad, associate,
  intern/internship, working student/werkstudent, trainee, praktikant, duales studium.
- *negative dict:* senior/sr., lead, principal, staff, director, head of, VP, chief, manager, expert.
**Lenient match (default)** = tech ∧ ¬negative; record matched_tech + seniority_label (junior/mid/graduate/… or
"Unspecified"). `--require-seniority` → strict (tech ∧ positive-seniority ∧ ¬negative). *(Risk: flashtext is old; if it
breaks on 3.13 fall back to `flashtext2`/`pyahocorasick` behind same interface; matching is case-insensitive, word-boundary.)*
`temporal.py`: ISO via datetime + relative strings via `dateparser` (langs incl. de: "Vor 2 Tagen","Heute") → epoch; keep if
≤ `window_hours` (**default 48**; `--all`/`--window-hours 0` disables the freshness filter to extract *all* matching
postings). *Test:* expanded title/desc table → expected match+seniority (incl. mid-level kept, senior rejected, plain
"Software Engineer" kept); German relative strings in/out of window; `--all` keeps old postings.

**P5 — Dedup + sink.** `dedup.py`: SQLite keyed by `sha256(direct_apply_url)`; `seen()/add()`, persists across runs.
`sink.py`: incremental append to CSV → finalize `.xlsx` (pandas+openpyxl) with exact cols: Company Name, Job Title,
Seniority Level, Matched Tech Stack, Location, Direct Apply URL, Source ATS, Timestamp. *Test:* dedup across 2 runs;
xlsx headers+rows correct (reopen & assert).

**P6 — DOM fallback (scrapling adaptive).** `scrapling install`. `dom.py`: static `Fetcher`/`AsyncFetcher` first;
SPA/anti-bot → `StealthyFetcher`/`DynamicFetcher`. Adaptive: locate job cards with CSS + `auto_save=True`; on change re-find
`adaptive=True`/`find_similar()`; adaptive SQLite path persistent (serverless caveat noted). Stealth concurrency semaphore
≤10 (8GB RAM limit). *Test (live, tolerant):* run vs 1–2 bespoke seed career pages; assert elements/list returned; adaptive
store file created.

**P7 — Net layer + discovery interfaces.** `net/throttle.py` per-domain async limiter + separate HTTP/browser concurrency
semaphores; `net/proxy.py` thread-safe `ProxyRotator` (no-op default, pluggable list/residential); `net/http.py` shared
`httpx.AsyncClient` + retries(tenacity)+gzip+UA rotation+timeouts. `discovery/`: `DiscoveryProvider` interface;
`csv_seed.py` working default (yields CompanyEntity from seed CSV); `serp.py`+`handelsregister.py` documented stubs that
raise clear "configure key/enable" errors. *Test:* throttle min-interval honored; proxy cycles; csv_seed yields rows;
stubs raise cleanly.

**P8 — Orchestrator (harness) + CLI + end-to-end.** `orchestrator.py`: async harness per company: classify → API-first
extractor (DOM fallback via probe) → temporal → semantic → dedup → sink. Concurrency semaphores + per-domain throttle;
per-company error isolation (one failure ≠ crash); checkpoint/resume (persist processed set + state to disk); periodic CSV
flush. `cli.py`: `python -m jobpipe run --seed … --window-hours 48 --out data/output/jobs.xlsx --concurrency N [--limit N]
[--all] [--require-seniority]`; plus `classify`/`extract-one` debug subcommands. **Extract-only** — no apply/submit path
anywhere. *Test (live):* CLI on `--limit 20` slice → xlsx produced, columns correct, rows junior/entry/mid/grad tech in
window (empty-tolerant); full `pytest` green.

**P9 — Docs + finalize.** README (architecture, install incl. `scrapling install`, usage, wiring SERP/Handelsregister/proxy
later, serverless persistence caveat for scrapling SQLite, concurrency/memory limits). Final full `pytest` + real CLI run
producing `data/output/jobs.xlsx`.

## Dependencies (requirements.txt)
`scrapling[fetchers]>=0.4.9`, `httpx`, `pydantic>=2`, `pydantic-settings`, `flashtext` (fallback flashtext2/pyahocorasick),
`dateparser`, `pandas`, `openpyxl`, `lxml`, `tenacity`, `python-dotenv`, `pyyaml`, `pytest`, `pytest-asyncio`. (`click`
optional; argparse fine.)

## Verification (end-to-end)
1. `source .venv/bin/activate`; per-phase `pytest tests/test_<phase>.py -q` live.
2. Final `pytest -q` (whole suite green).
3. `python -m jobpipe run --seed data/seed_companies.csv --limit 20 --window-hours 48 --out data/output/jobs.xlsx`; open
   xlsx, confirm 8 columns + only entry/associate/intern tech rows within 48h, direct apply URLs (no aggregators).
4. Re-run → dedup prevents duplicate rows.

## Out of scope now (interfaced, unconfigured)
500K Handelsregister gazette crawl, SERP discovery, residential-proxy/CAPTCHA solving, serverless deploy — code-complete
interfaces + docs only (need paid keys/infra to run).

## Unresolved questions
- Freshness window: default **48h**; `--all` extracts every matching posting regardless of date. Keep 48h default?
- Seed CSV: keep non-DE / global-hub entries (Google/Adobe/IBM Munich hubs)? Default: keep.
- Output `data/output/jobs.xlsx` & no `git init`? Default: yes / no.
