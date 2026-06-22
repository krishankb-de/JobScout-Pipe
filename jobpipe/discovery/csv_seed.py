"""Working default discovery: read companies from the seed CSV."""
from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from ..models import CompanyEntity
from .base import DiscoveryProvider


class CsvSeedDiscovery(DiscoveryProvider):
    name = "csv_seed"

    def __init__(self, path: str | Path, *, limit: int | None = None):
        self.path = Path(path)
        self.limit = limit

    def __iter__(self) -> Iterator[CompanyEntity]:
        with self.path.open(encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                if self.limit is not None and i >= self.limit:
                    return
                url = (row.get("career_url") or "").strip()
                if not url.lower().startswith(("http://", "https://")):
                    continue
                yield CompanyEntity(
                    name=row.get("company", "").strip(),
                    career_url=url,
                    sector=row.get("sector", "").strip(),
                    city=row.get("city", "").strip(),
                    source=row.get("source", "csv_seed").strip() or "csv_seed",
                )
