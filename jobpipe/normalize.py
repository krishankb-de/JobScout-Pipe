"""Shared helpers to normalize provider payloads into RawJob fields."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from lxml import html as lxml_html

_WS_RE = re.compile(r"\s+")


def clean_ws(s: str | None) -> str:
    return _WS_RE.sub(" ", (s or "").replace("\xa0", " ")).strip()


def strip_html(s: str | None) -> str:
    """HTML (possibly entity-encoded, e.g. Greenhouse) -> collapsed plain text."""
    if not s:
        return ""
    s = html.unescape(s)
    if "<" in s and ">" in s:
        try:
            s = lxml_html.fromstring(s).text_content()
        except Exception:
            s = re.sub(r"<[^>]+>", " ", s)
    return clean_ws(s)


def epoch_ms_to_dt(ms) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def parse_iso(s: str | None) -> datetime | None:
    """Parse an ISO 8601 string to an aware UTC datetime (None on failure)."""
    if not s:
        return None
    txt = s.strip()
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        # date-only or odd formats
        try:
            dt = datetime.fromisoformat(txt[:10])
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def abs_url(base: str, path: str) -> str:
    if not path:
        return ""
    if path.startswith(("http://", "https://")):
        return path
    return urljoin(base, path)


def join_nonempty(*parts: str, sep: str = ", ") -> str:
    return sep.join(p.strip() for p in parts if p and p.strip())
