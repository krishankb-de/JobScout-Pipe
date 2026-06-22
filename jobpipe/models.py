"""Core data models: ATS taxonomy, company entities, raw + normalized jobs.

`RawJob`  = a posting as extracted from a provider (pre-filter).
`NormalizedJob` = an output row after semantic/temporal filtering, with the exact
8 columns the Excel sink expects.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ATSType(str, Enum):
    """Applicant Tracking System families we can detect from a career URL."""

    LEVER = "lever"
    GREENHOUSE = "greenhouse"
    PERSONIO = "personio"
    WORKDAY = "workday"
    SUCCESSFACTORS = "successfactors"
    JOIN = "join"
    ASHBY = "ashby"
    SMARTRECRUITERS = "smartrecruiters"
    RECRUITEE = "recruitee"
    BREEZY = "breezy"
    WORKABLE = "workable"
    SOFTGARDEN = "softgarden"
    TEAMTAILOR = "teamtailor"
    UNKNOWN = "unknown"

    @property
    def has_native_extractor(self) -> bool:
        """True for ATS platforms with a dedicated API-first extractor (Phase 3)."""
        return self in _NATIVE_EXTRACTORS


# The 5 platforms the brief mandates and Phase 3 implements natively.
_NATIVE_EXTRACTORS = {
    ATSType.LEVER,
    ATSType.PERSONIO,
    ATSType.WORKDAY,
    ATSType.SUCCESSFACTORS,
    ATSType.JOIN,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def canonical_url(url: str) -> str:
    """Normalize a URL for dedup keys: lowercase scheme/host, drop trailing slash/fragment."""
    u = (url or "").strip()
    if "#" in u:
        u = u.split("#", 1)[0]
    return u.rstrip("/")


class CompanyEntity(BaseModel):
    """A company to crawl: name + career URL, enriched with detected ATS."""

    model_config = ConfigDict(extra="ignore")

    name: str
    career_url: str
    sector: str = ""
    city: str = ""
    country: str = "DE"
    source: str = ""  # corporate | startup | serp | handelsregister
    ats: ATSType = ATSType.UNKNOWN
    ats_meta: dict = Field(default_factory=dict)  # e.g. {tenant, site, shard} / {client} / {subdomain}

    @field_validator("career_url")
    @classmethod
    def _require_http(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError(f"career_url must be http(s): {v!r}")
        return v


class RawJob(BaseModel):
    """A posting as extracted from a provider, before filtering/normalization."""

    model_config = ConfigDict(extra="ignore")

    company: str
    title: str
    apply_url: str  # direct apply/canonical URL — recorded only, never actioned
    listing_url: str = ""
    location: str = ""
    description: str = ""  # plain text (HTML stripped)
    posted_at: datetime | None = None
    posted_at_text: str | None = None  # raw/relative string when no parseable datetime
    source_ats: ATSType = ATSType.UNKNOWN
    employment_type: str = ""  # full-time, part-time, internship, ...
    workplace_type: str = ""  # remote | hybrid | onsite
    department: str = ""
    job_id: str = ""


# Exact output column order for the Excel/CSV sink.
OUTPUT_COLUMNS = [
    "Company Name",
    "Job Title",
    "Seniority Level",
    "Matched Tech Stack",
    "Location",
    "Direct Apply URL",
    "Source ATS",
    "Timestamp",
]


class NormalizedJob(BaseModel):
    """A filtered, output-ready posting mapping to the 8 sink columns."""

    model_config = ConfigDict(extra="ignore")

    company: str
    title: str
    seniority: str = "Unspecified"
    matched_tech: list[str] = Field(default_factory=list)
    matched_roles: list[str] = Field(default_factory=list)
    location: str = ""
    apply_url: str
    source_ats: ATSType = ATSType.UNKNOWN
    posted_at: datetime | None = None
    extracted_at: datetime = Field(default_factory=utcnow)
    description: str = ""  # retained for reference; not exported

    def dedup_key(self) -> str:
        return hashlib.sha256(canonical_url(self.apply_url).encode("utf-8")).hexdigest()

    def to_row(self) -> dict:
        """Return the exact 8-column output row."""
        return {
            "Company Name": self.company,
            "Job Title": self.title,
            "Seniority Level": self.seniority,
            "Matched Tech Stack": ", ".join(self.matched_tech),
            "Location": self.location,
            "Direct Apply URL": self.apply_url,
            "Source ATS": self.source_ats.value,
            "Timestamp": self.extracted_at.astimezone(timezone.utc).isoformat(),
        }

    @classmethod
    def from_raw(
        cls,
        raw: RawJob,
        *,
        seniority: str,
        matched_tech: list[str],
        matched_roles: list[str] | None = None,
    ) -> "NormalizedJob":
        return cls(
            company=raw.company,
            title=raw.title,
            seniority=seniority,
            matched_tech=matched_tech,
            matched_roles=matched_roles or [],
            location=raw.location,
            apply_url=raw.apply_url,
            source_ats=raw.source_ats,
            posted_at=raw.posted_at,
            description=raw.description,
        )
