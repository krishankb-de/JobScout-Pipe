"""Freshness filtering: resolve a posting's publish time and test the window.

Exact ISO timestamps are used directly; relative/localized strings (Workday's
"Posted 3 Days Ago", German "Vor 2 Tagen") are parsed with dateparser.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import dateparser

from ..models import RawJob, utcnow

# Strip framing words so dateparser sees only the relative phrase.
_STRIP_RE = re.compile(
    r"\b(posted|gepostet|active\s+since|aktiv\s+seit|ver[öo]ffentlicht(\s+am)?|publiziert|on)\b",
    re.IGNORECASE,
)
_DP_SETTINGS = {
    "PREFER_DATES_FROM": "past",
    "RETURN_AS_TIMEZONE_AWARE": True,
}


def parse_relative(text: str | None, now: datetime | None = None) -> datetime | None:
    if not text:
        return None
    s = _STRIP_RE.sub(" ", text).replace("+", " ").strip(" .,-")
    if not s:
        return None
    dt = dateparser.parse(
        s, languages=["en", "de"],
        settings={**_DP_SETTINGS, "RELATIVE_BASE": now or utcnow()},
    )
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def resolve_posted_at(raw: RawJob, now: datetime | None = None) -> datetime | None:
    """Exact timestamp if present, else parse the relative/localized text."""
    if raw.posted_at:
        return raw.posted_at.astimezone(timezone.utc)
    return parse_relative(raw.posted_at_text, now)


def passes_window(
    dt: datetime | None,
    window_hours: int,
    now: datetime | None = None,
    *,
    keep_undated: bool = False,
) -> bool:
    """True if dt is within the last `window_hours`. window_hours==0 keeps all.

    Undated postings are dropped when filtering (precision) unless keep_undated.
    A small forward skew (+24h) tolerates timezone/clock differences.
    """
    if window_hours == 0:
        return True
    if dt is None:
        return keep_undated
    now = now or utcnow()
    earliest = now - timedelta(hours=window_hours)
    latest = now + timedelta(hours=24)
    return earliest <= dt <= latest
