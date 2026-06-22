"""Phase 4: semantic + temporal filtering."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from jobpipe.filtering.semantic import SemanticMatcher
from jobpipe.filtering.temporal import parse_relative, passes_window, resolve_posted_at
from jobpipe.models import RawJob
from tests.conftest import REPO_ROOT

KW = REPO_ROOT / "config" / "keywords.yaml"
NOW = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def matcher():
    return SemanticMatcher(KW)


@pytest.fixture(scope="module")
def strict():
    return SemanticMatcher(KW, require_seniority=True)


# --- semantic: positives -------------------------------------------------
@pytest.mark.parametrize("title,seniority", [
    ("Junior Backend Engineer (m/w/d)", "Junior"),
    ("Software Engineer", "Unspecified"),
    ("Mid-Level Java Developer", "Mid Level"),
    ("Graduate Software Developer", "Graduate"),
    ("Working Student - Backend Developer (m/f/d)", "Working Student"),
    ("Praktikum Full Stack Developer", "Intern"),
    ("Entry Level Python Developer", "Entry Level"),
    ("AI Engineer", "Unspecified"),
    ("Werkstudent Java Entwickler (m/w/d)", "Working Student"),
    ("Data Analyst", "Unspecified"),
    ("Junior Data Engineer (m/w/d)", "Junior"),
    ("Data Scientist - NLP", "Unspecified"),
    ("Working Student Data Engineering", "Working Student"),
])
def test_semantic_matches(matcher, title, seniority):
    r = matcher.match(title)
    assert r is not None, f"expected match for {title!r}"
    assert r.seniority == seniority


# --- semantic: negatives -------------------------------------------------
@pytest.mark.parametrize("title", [
    "Senior Software Engineer",
    "Lead Python Developer",
    "Principal Backend Engineer",
    "Engineering Manager",
    "Head of Engineering",
    "Junior Sales Engineer",         # negative role wins
    "Account Executive",
    "Mechanical Engineer",
    "Product Manager",
    "UX Designer",
    "Marketing Specialist",          # no tech role at all
    "Business Analyst",              # bare "analyst" is not a data role
    "Financial Analyst",
])
def test_semantic_rejects(matcher, title):
    assert matcher.match(title) is None


def test_matched_tech_falls_back_to_role_label(matcher):
    r = matcher.match("Backend Engineer")  # no explicit stack token in title
    assert r is not None and r.matched_tech == ["Backend"]


def test_matched_tech_extracts_stack_tokens(matcher):
    r = matcher.match("Backend Engineer", description="You will use Python, Kafka and AWS.")
    assert "Python" in r.matched_tech


def test_cpp_token_matches_special_boundary(matcher):
    r = matcher.match("C++ Developer")
    assert r is not None and "C++" in r.matched_tech


def test_strict_mode_requires_seniority(matcher, strict):
    assert matcher.match("Software Engineer") is not None       # lenient keeps it
    assert strict.match("Software Engineer") is None            # strict drops untagged
    assert strict.match("Junior Software Engineer") is not None


# --- temporal ------------------------------------------------------------
def test_exact_timestamp_window():
    recent = NOW - timedelta(hours=2)
    old = NOW - timedelta(days=3)
    assert passes_window(recent, 48, now=NOW) is True
    assert passes_window(old, 48, now=NOW) is False
    assert passes_window(old, 0, now=NOW) is True       # 0 = keep all
    assert passes_window(old, 100, now=NOW) is True


@pytest.mark.parametrize("text,within48", [
    ("Posted Today", True),
    ("Posted Yesterday", True),
    ("Posted 3 Days Ago", False),
    ("Posted 30+ Days Ago", False),
    ("Vor 1 Tag", True),
    ("Vor 2 Tagen", True),
    ("Vor 5 Tagen", False),
])
def test_relative_strings(text, within48):
    dt = parse_relative(text, now=NOW)
    assert dt is not None, f"failed to parse {text!r}"
    assert passes_window(dt, 48, now=NOW) is within48


def test_undated_dropped_unless_keep():
    assert passes_window(None, 48, now=NOW) is False
    assert passes_window(None, 48, now=NOW, keep_undated=True) is True
    assert passes_window(None, 0, now=NOW) is True


def test_resolve_posted_at_prefers_exact():
    raw = RawJob(company="X", title="t", apply_url="https://x/1",
                 posted_at=NOW - timedelta(hours=1), posted_at_text="Posted 9 Days Ago")
    assert resolve_posted_at(raw, NOW) == (NOW - timedelta(hours=1))
    raw2 = RawJob(company="X", title="t", apply_url="https://x/2", posted_at_text="Posted Today")
    assert resolve_posted_at(raw2, NOW) is not None
