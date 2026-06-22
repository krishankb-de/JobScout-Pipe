"""Detect the ATS behind a career URL.

`classify_url` is pure (host/path/query regex). `probe_url` is an optional async
HTTP fetch that refines UNKNOWN sites by inspecting the final redirect host and
scanning the page body for an embedded ATS URL (bespoke career pages usually
link/iframe their ATS), extracting its identifier.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from .models import ATSType

WORKDAY_HOST_RE = re.compile(
    r"^(?P<tenant>[^.]+)\.(?P<shard>wd\d+)\.myworkday(?:jobs|site)\.com$", re.IGNORECASE
)
_LOCALE_RE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")

# Path segments that are framework noise, never the board identifier.
_GH_SKIP = {"embed", "v1", "boards", "job_board", "js", "jobs", "departments", "job_app", "v3"}
_SR_SKIP = {"widget", "v1", "companies", "postings", "candidate", "app", "jobs"}


def _workday_meta(host: str, segs: list[str]) -> dict:
    m = WORKDAY_HOST_RE.match(host)
    meta = {"tenant": m.group("tenant"), "shard": m.group("shard")} if m else {}
    site_segs = [s for s in segs if not _LOCALE_RE.match(s) and s != "wday"]
    if site_segs:
        meta["site"] = site_segs[0]
    return meta


def _greenhouse_token(host: str, segs: list[str], q: dict) -> str:
    if "for" in q and q["for"]:
        return q["for"][0]
    if "boards" in segs:  # .../v1/boards/{token}/...
        i = segs.index("boards")
        if i + 1 < len(segs):
            return segs[i + 1]
    for s in segs:
        if s not in _GH_SKIP:
            return s
    return ""


def _ashby_org(segs: list[str]) -> str:
    if "job-board" in segs:  # api.ashbyhq.com/posting-api/job-board/{org}
        i = segs.index("job-board")
        return segs[i + 1] if i + 1 < len(segs) else ""
    return segs[0] if segs else ""


def _sr_company(segs: list[str]) -> str:
    if "companies" in segs:  # api.smartrecruiters.com/v1/companies/{company}/postings
        i = segs.index("companies")
        return segs[i + 1] if i + 1 < len(segs) else ""
    for s in segs:
        if s not in _SR_SKIP:
            return s
    return ""


def classify_url(url: str) -> tuple[ATSType, dict]:
    """Return (ATSType, ats_meta) for a career URL from host/path/query alone."""
    sp = urlsplit(url)
    host = (sp.hostname or "").lower()
    segs = [s for s in sp.path.split("/") if s]
    q = parse_qs(sp.query)
    if not host:
        return ATSType.UNKNOWN, {}

    if WORKDAY_HOST_RE.match(host):
        return ATSType.WORKDAY, _workday_meta(host, segs)

    if host.endswith(".jobs.personio.de") or host.endswith(".jobs.personio.com"):
        return ATSType.PERSONIO, {"subdomain": host.split(".")[0]}

    if host == "api.lever.co":
        client = segs[2] if len(segs) >= 3 and segs[0] == "v0" and segs[1] == "postings" else (segs[-1] if segs else "")
        return ATSType.LEVER, {"client": client}
    if host == "jobs.lever.co":
        return ATSType.LEVER, {"client": segs[0] if segs else ""}

    if host.endswith(".greenhouse.io") or host == "grnh.se":
        return ATSType.GREENHOUSE, {"token": _greenhouse_token(host, segs, q)}

    if host.endswith(".ashbyhq.com"):
        return ATSType.ASHBY, {"org": _ashby_org(segs)}

    if host == "smartrecruiters.com" or host.endswith(".smartrecruiters.com"):
        return ATSType.SMARTRECRUITERS, {"company": _sr_company(segs)}

    if host.endswith(".recruitee.com"):
        return ATSType.RECRUITEE, {"company": host.split(".")[0]}

    if host.endswith(".breezy.hr"):
        return ATSType.BREEZY, {"subdomain": host.split(".")[0]}

    if host.endswith("workable.com"):
        return ATSType.WORKABLE, {"account": segs[0] if segs else ""}

    if host.endswith(".teamtailor.com"):
        return ATSType.TEAMTAILOR, {"subdomain": host.split(".")[0]}

    if "softgarden" in host:
        return ATSType.SOFTGARDEN, {}

    if any(s in host for s in ("successfactors", "sapsf", "jobs2web")):
        return ATSType.SUCCESSFACTORS, {}

    if host == "join.com" or host.endswith(".join.com"):
        return ATSType.JOIN, {}

    return ATSType.UNKNOWN, {}


# Substrings that betray an ATS when found in the final URL or page body.
ATS_BODY_SIGNATURES: list[tuple[ATSType, tuple[str, ...]]] = [
    (ATSType.WORKDAY, ("myworkdayjobs.com", "myworkdaysite.com", "/wday/")),
    (ATSType.PERSONIO, (".jobs.personio.de", ".jobs.personio.com", "personio.de/xml")),
    (ATSType.LEVER, ("jobs.lever.co", "api.lever.co")),
    (ATSType.GREENHOUSE, ("greenhouse.io", "grnh.se")),
    (ATSType.ASHBY, ("ashbyhq.com",)),
    (ATSType.SMARTRECRUITERS, ("smartrecruiters.com",)),
    (ATSType.JOIN, ("join.com/api", "api.join.com")),
    (ATSType.RECRUITEE, (".recruitee.com",)),
    (ATSType.WORKABLE, ("workable.com",)),
    (ATSType.TEAMTAILOR, (".teamtailor.com",)),
    (ATSType.SOFTGARDEN, ("softgarden",)),
    (ATSType.SUCCESSFACTORS, ("successfactors", "sapsf", "jobs2web")),
]

_URL_RE = re.compile(r"https?:\\?/\\?/[^\s\"'<>\\)]+", re.IGNORECASE)


def _identify_from_body(body: str) -> tuple[ATSType, dict]:
    """Find an embedded ATS URL in page HTML and classify it (yields identifiers)."""
    for cand, sigs in ATS_BODY_SIGNATURES:
        for m in _URL_RE.finditer(body):
            u = m.group(0).replace("\\/", "/")
            if any(sig in u.lower() for sig in sigs):
                ats, meta = classify_url(u)
                if ats is not ATSType.UNKNOWN:
                    return ats, {**meta, "discovered_url": u, "via": "body-probe"}
    low = body.lower()
    for cand, sigs in ATS_BODY_SIGNATURES:
        if any(sig in low for sig in sigs):
            return cand, {"via": "body-probe"}
    return ATSType.UNKNOWN, {}


async def probe_url(url: str, *, timeout: float = 12.0, max_bytes: int = 400_000) -> tuple[ATSType, dict]:
    """Best-effort live refinement of UNKNOWN: follow redirects + scan body.

    Classifies the final (redirected) URL first; if still UNKNOWN, scans the page
    body for an embedded ATS URL and extracts its identifier. Network errors
    degrade gracefully to (UNKNOWN, {}).
    """
    import httpx

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 jobpipe/0.1"})
    except Exception:
        return ATSType.UNKNOWN, {}

    final = str(resp.url)
    ats, meta = classify_url(final)
    if ats is not ATSType.UNKNOWN:
        return ats, meta

    body = (resp.text or "")[:max_bytes]
    return _identify_from_body(body)
