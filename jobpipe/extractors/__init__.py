"""Extractor registry: map an ATSType to its API-first extractor."""
from __future__ import annotations

import httpx

from ..models import ATSType
from .ashby import AshbyExtractor
from .base import BaseExtractor, ExtractorError
from .greenhouse import GreenhouseExtractor
from .join import JoinExtractor
from .lever import LeverExtractor
from .personio import PersonioExtractor
from .smartrecruiters import SmartRecruitersExtractor
from .successfactors import SuccessFactorsExtractor
from .workday import WorkdayExtractor

REGISTRY: dict[ATSType, type[BaseExtractor]] = {
    ATSType.LEVER: LeverExtractor,
    ATSType.PERSONIO: PersonioExtractor,
    ATSType.WORKDAY: WorkdayExtractor,
    ATSType.SUCCESSFACTORS: SuccessFactorsExtractor,
    ATSType.JOIN: JoinExtractor,
    ATSType.GREENHOUSE: GreenhouseExtractor,
    ATSType.ASHBY: AshbyExtractor,
    ATSType.SMARTRECRUITERS: SmartRecruitersExtractor,
}

SUPPORTED_ATS = frozenset(REGISTRY)


def get_extractor(ats: ATSType, client: httpx.AsyncClient) -> BaseExtractor | None:
    cls = REGISTRY.get(ats)
    return cls(client) if cls else None


__all__ = [
    "REGISTRY",
    "SUPPORTED_ATS",
    "get_extractor",
    "BaseExtractor",
    "ExtractorError",
    "AshbyExtractor",
    "GreenhouseExtractor",
    "JoinExtractor",
    "LeverExtractor",
    "PersonioExtractor",
    "SmartRecruitersExtractor",
    "SuccessFactorsExtractor",
    "WorkdayExtractor",
]
