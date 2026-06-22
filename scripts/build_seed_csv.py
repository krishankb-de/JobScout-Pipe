"""Build data/seed_companies.csv from the provided raw company lists.

Reads data/raw/corporates.txt (Company | Sector | City | URL) and
data/raw/startups.txt (Company | City / Sector | URL), cleans/validates the
career URLs, normalises the schema to (company, sector, city, career_url,
source), de-duplicates, and writes the seed CSV.

Run:  python scripts/build_seed_csv.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "seed_companies.csv"

FIELDNAMES = ["company", "sector", "city", "career_url", "source"]
URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def clean_url(raw: str) -> str:
    """Strip wrapping parens/whitespace and surrounding quotes from a URL cell."""
    u = raw.strip()
    # The brief's lists wrap a couple of URLs in parentheses, e.g. "(https://...)".
    while u and u[0] in "(<" and u[-1] in ")>":
        u = u[1:-1].strip()
    return u.strip().strip('"').strip()


def split_city_sector(value: str) -> tuple[str, str]:
    """Startup rows store location as 'City / Sector' in one cell."""
    if " / " in value:
        city, sector = value.split(" / ", 1)
        return city.strip(), sector.strip()
    return value.strip(), ""


def parse_line(line: str, schema: str) -> dict | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = [p.strip() for p in line.split("|")]
    if schema == "corporate":
        if len(parts) < 4:
            return None
        company, sector, city, url = parts[0], parts[1], parts[2], parts[3]
    else:  # startup: Company | City / Sector | URL
        if len(parts) < 3:
            return None
        company = parts[0]
        city, sector = split_city_sector(parts[1])
        url = parts[2]
    url = clean_url(url)
    if not company or not URL_RE.match(url):
        return None
    return {
        "company": company,
        "sector": sector,
        "city": city,
        "career_url": url,
        "source": schema,
    }


def parse_file(path: Path, schema: str) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = parse_line(line, schema)
        if row:
            rows.append(row)
    return rows


def dedupe(rows: list[dict]) -> list[dict]:
    """Drop exact duplicate career URLs (keep first), case-insensitive."""
    seen: set[str] = set()
    out = []
    for r in rows:
        key = r["career_url"].rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def build() -> list[dict]:
    rows = parse_file(RAW / "corporates.txt", "corporate")
    rows += parse_file(RAW / "startups.txt", "startup")
    return dedupe(rows)


def main() -> int:
    rows = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    corp = sum(1 for r in rows if r["source"] == "corporate")
    start = sum(1 for r in rows if r["source"] == "startup")
    print(f"Wrote {len(rows)} companies to {OUT.relative_to(ROOT)} "
          f"(corporate={corp}, startup={start})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
