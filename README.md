# jobpipe — German Tech-Job Extraction Pipeline

Automated **extraction** of entry / junior / mid-level / graduate software roles
(AI·ML, backend, Python, Java, full-stack, software engineer/developer, …) from
German company career pages. ATS-first with an adaptive
[scrapling](https://github.com/D4Vinci/Scrapling) DOM fallback, filtered to a
rolling freshness window, written to a precision Excel workbook of **direct apply
URLs**.

> ## ⚠️ Extraction only
> This tool **reads and records** postings. It never applies, autofills forms,
> logs in, or submits anything — the apply URL is just a column in the output.

Verified end-to-end on the bundled seed of 259 German companies: a single
`--all` run extracted **154** matching tech roles from 1,475 raw postings across
Workday, Greenhouse, SmartRecruiters, Personio, Ashby and bespoke career sites.

---

## How it works

```
discovery → classify (URL) → probe (live) → extract (ATS API | adaptive DOM)
          → temporal filter (24–48h) → semantic filter (role+seniority)
          → dedup (sqlite) → Excel sink
```

1. **Discovery** — where companies come from. Default `CsvSeedDiscovery` reads
   `data/seed_companies.csv`. SERP + Handelsregister providers are interface
   stubs for scaling to all German companies (see *Scaling* below).
2. **Classify** (`classify.py`) — detect the ATS from the career URL alone.
3. **Probe** — most branded career pages aren't the ATS itself, so an UNKNOWN
   URL is fetched once and its body scanned for the embedded ATS board (and its
   identifier — Lever client, Personio subdomain, Workday tenant, …).
4. **Extract** (`extractors/`) — API-first per ATS; bespoke/unknown sites fall
   back to scrapling's adaptive DOM extraction.
5. **Filter** (`filtering/`) — title-driven role/seniority match (FlashText) and
   a freshness window (dateparser handles ISO + relative/German strings).
6. **Dedup** (`dedup.py`) — a persistent SQLite store keyed by apply-URL hash so
   repeat daily runs never write a posting twice.
7. **Sink** (`sink.py`) — append-only CSV compiled to a formatted `.xlsx`.

The whole thing is an async **harness** (`orchestrator.py`): per-domain
throttling, split HTTP/browser concurrency budgets, per-company error isolation
(one failure never stops the run), and checkpoint/resume.

## Supported ATS

| ATS | Endpoint | Auth | Notes |
|---|---|---|---|
| Lever | `api.lever.co/v0/postings/{client}` | none | fully structured |
| Personio | `{sub}.jobs.personio.{de,com}/xml` | none | iterates `.de`/`.com` |
| Workday | `POST /wday/cxs/{tenant}/{site}/jobs` | none | paginates + facet-fragments the 2,000 cap |
| SuccessFactors | `POST /services/recruiting/v1/jobs` | CSRF | best-effort (locale-isolated, CAPTCHA) |
| Join.com | `join.com/api/public/companies/{id}/jobs` | none | needs integer company_id |
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{token}/jobs` | none | bonus (high seed yield) |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{org}` | none | bonus |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/{co}/postings` | none | bonus |
| *anything else* | adaptive DOM (scrapling) | — | static fetch → stealth browser |

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"        # or: pip install -r requirements.txt
scrapling install               # one-time: stealth browser for the DOM fallback
python scrapling install        # (equivalent) downloads Chromium + camoufox
```
Requires Python ≥ 3.10 (developed on 3.13).

## Usage

```bash
# Build/refresh the seed CSV from the provided raw lists
python scripts/build_seed_csv.py

# Full run, last 48h, write Excel (default window)
python -m jobpipe run --out data/output/jobs.xlsx

# Extract ALL matching roles regardless of date (no freshness filter)
python -m jobpipe run --all

# First 20 companies, strict (require an explicit junior/entry/mid/grad token)
python -m jobpipe run --limit 20 --require-seniority

# Debug a single career URL
python -m jobpipe classify https://boards.greenhouse.io/contentful
python -m jobpipe extract-one https://giant-swarm.jobs.personio.de/ --name "Giant Swarm"
```

Key `run` flags: `--all` (disable window), `--window-hours N`, `--require-seniority`,
`--limit N`, `--concurrency N`, `--no-browser` (skip stealth fallback),
`--keep-undated`, `--resume`/`--fresh` (checkpointing).

## Output schema (`jobs.xlsx`)

`Company Name` · `Job Title` · `Seniority Level` · `Matched Tech Stack` ·
`Location` · `Direct Apply URL` · `Source ATS` · `Timestamp`

## What matches

Editable in **`config/keywords.yaml`**:
- **Roles** (in the title): software/backend/frontend/full-stack/web engineer &
  developer, Python/Java/AI·ML, **data (engineer, scientist, analyst, analytics,
  BI)**, DevOps/cloud/mobile, bare developer/engineer, and German
  `Entwickler`/`Softwareentwickler`.
- **Seniority** (positive): junior, entry, **mid-level**, graduate, working
  student, intern, trainee, associate, dual-study.
- **Negative** (drop): senior, lead, principal, staff, director, head, manager,
  architect — plus non-dev roles (sales, mechanical, customer support, …).

Logic (lenient, default): *tech role in title* ∧ *no negative token*. A plain
"Software Engineer" is kept as `Unspecified` seniority. `--require-seniority`
tightens to require a junior/entry/mid/grad token. Matching is case-insensitive
and word-boundary aware, so body text never causes false exclusions.

## Configuration

Copy `.env.example` → `.env` (env prefix `JOBPIPE_`). Notable settings:
`WINDOW_HOURS` (0 = keep all), `REQUIRE_SENIORITY`, `HTTP_CONCURRENCY`,
`BROWSER_CONCURRENCY` (≤10), `PER_DOMAIN_DELAY`, `WORKDAY_MAX_JOBS`, the output/
state/adaptive paths, and the optional `PROXY_URLS` / `SERP_API_KEY`.

## Scaling to all German companies

The brief targets ~500K companies. The runnable build covers the full
**extraction** path on the seed; the **discovery** + **anti-bot** layers are
code-complete interfaces, unconfigured here:

- **Handelsregister** (`discovery/handelsregister.py`) — iterate the free,
  sequentially-numbered Gazette notices to build the ~2.3M active-company
  universe (names only).
- **SERP** (`discovery/serp.py`) — resolve each company name to its direct
  career/ATS domain via a SERP API (set `JOBPIPE_SERP_API_KEY`).
- **Proxies** (`net/proxy.py`) — `ProxyRotator` is a no-op by default; populate
  `JOBPIPE_PROXY_URLS` (residential recommended for CAPTCHA-heavy SuccessFactors).

**Operational limits baked in:** stealth-browser concurrency is hard-capped at 10
(>10 concurrent Chromium sessions exhaust 8GB RAM); Workday requests are spaced
and capped; per-domain throttling protects targets/WAFs.

**Serverless caveat:** scrapling's adaptive element fingerprints live in a SQLite
file (`JOBPIPE_ADAPTIVE_DB`). On AWS Lambda/ECS this is wiped on container exit
unless you **mount a persistent volume** (or sync to a shared DB) — otherwise
auto-healing is neutralized and DOM extraction turns brittle. Same for the dedup
store (`JOBPIPE_STATE_DB`).

## Testing

```bash
pytest -q                       # full suite (124 tests; hits live ATS endpoints)
pytest -m "not live" -q         # offline-only subset
pytest -m browser -q            # stealth-browser smoke
```
Per the project decision, tests hit **live** ATS endpoints against stable real
boards; they tolerate transient network failures (skip) and empty windows.

## Project layout

```
jobpipe/
  config.py models.py classify.py normalize.py dedup.py sink.py orchestrator.py cli.py
  extractors/  {lever,personio,workday,successfactors,join,greenhouse,ashby,smartrecruiters,dom}.py
  filtering/   {semantic,temporal}.py
  discovery/   {csv_seed,serp,handelsregister}.py
  net/         {http,proxy,throttle}.py
scripts/build_seed_csv.py   config/keywords.yaml   data/seed_companies.csv   tests/
```

## Known limitations / future work

- No geo-filter: German companies with global hubs (e.g. Rohde & Schwarz) list
  worldwide roles; add a location filter if Germany-only is required.
- SuccessFactors legacy Recruiting-Marketing portals lack the v1 API → best-effort.
- Join.com needs an integer `company_id` (a discovery step); none appear in the seed.
- Bare "engineer"/"developer" favors recall over precision — tune
  `config/keywords.yaml` (e.g. `--require-seniority`) to tighten.
```
