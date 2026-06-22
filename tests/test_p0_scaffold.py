"""Phase 0: scaffold + seed data sanity."""
from __future__ import annotations

import csv
import re

import yaml

import jobpipe
from tests.conftest import REPO_ROOT

URL_RE = re.compile(r"^https?://", re.IGNORECASE)
SEED_CSV = REPO_ROOT / "data" / "seed_companies.csv"
KEYWORDS = REPO_ROOT / "config" / "keywords.yaml"


def test_package_imports_with_version():
    assert jobpipe.__version__


def _load_seed():
    with SEED_CSV.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_seed_csv_exists_and_has_expected_columns():
    rows = _load_seed()
    assert rows, "seed CSV is empty"
    assert set(rows[0].keys()) == {"company", "sector", "city", "career_url", "source"}


def test_seed_csv_row_count():
    rows = _load_seed()
    assert len(rows) >= 250, f"expected >=250 companies, got {len(rows)}"


def test_all_seed_urls_are_valid_http():
    rows = _load_seed()
    bad = [r["career_url"] for r in rows if not URL_RE.match(r["career_url"])]
    assert not bad, f"non-http(s) URLs found: {bad[:5]}"


def test_no_wrapping_parens_left_in_urls():
    rows = _load_seed()
    bad = [r["career_url"] for r in rows if r["career_url"].startswith("(") or r["career_url"].endswith(")")]
    assert not bad, f"URLs still wrapped in parens: {bad}"


def test_seed_urls_are_deduped():
    rows = _load_seed()
    keys = [r["career_url"].rstrip("/").lower() for r in rows]
    assert len(keys) == len(set(keys)), "duplicate career URLs in seed CSV"


def test_keywords_yaml_structure():
    data = yaml.safe_load(KEYWORDS.read_text(encoding="utf-8"))
    for key in ("tech_roles", "tech_stack", "seniority", "negative_seniority", "negative_roles"):
        assert key in data, f"missing '{key}' in keywords.yaml"
    # expanded targets the user asked for are present
    flat_roles = " ".join(
        v for vals in data["tech_roles"].values() for v in vals
    ).lower()
    for needle in ("java", "full stack", "software developer", "ai engineer"):
        assert needle in flat_roles, f"expected role variant '{needle}' missing"
    assert "Mid Level" in data["seniority"]
    assert "Graduate" in data["seniority"]
