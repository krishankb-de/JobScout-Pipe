"""Title-driven role/seniority matching via FlashText.

A posting matches when its TITLE contains a tech-role token and no negative
seniority/role token. Seniority is read from the title (then description). In
strict mode a positive seniority token is also required. The "Matched Tech Stack"
is collected from title+description (falling back to role labels).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from flashtext import KeywordProcessor


@dataclass
class MatchResult:
    seniority: str
    matched_tech: list[str] = field(default_factory=list)
    matched_roles: list[str] = field(default_factory=list)


def _kp(case_sensitive: bool = False, extra_boundaries: str = "") -> KeywordProcessor:
    kp = KeywordProcessor(case_sensitive=case_sensitive)
    for ch in extra_boundaries:
        kp.add_non_word_boundary(ch)
    return kp


def _labelled(mapping: dict[str, list[str]], extra_boundaries: str = "") -> KeywordProcessor:
    kp = _kp(extra_boundaries=extra_boundaries)
    for label, variants in mapping.items():
        for v in variants:
            kp.add_keyword(str(v), label)
    return kp


def _wordset(words: list[str]) -> KeywordProcessor:
    kp = _kp()
    for w in words:
        kp.add_keyword(str(w))
    return kp


def _uniq(seq) -> list[str]:
    return list(dict.fromkeys(seq))


class SemanticMatcher:
    def __init__(self, keywords_path: str | Path, *, require_seniority: bool = False):
        cfg = yaml.safe_load(Path(keywords_path).read_text(encoding="utf-8"))
        self.require_seniority = require_seniority
        self._roles = _labelled(cfg["tech_roles"])
        self._stack = _labelled(cfg["tech_stack"], extra_boundaries="+#.")
        self._sen = _labelled(cfg["seniority"])
        self._sen_order = list(cfg["seniority"].keys())  # priority = YAML order
        self._neg_sen = _wordset(cfg["negative_seniority"])
        self._neg_role = _wordset(cfg["negative_roles"])

    def _seniority(self, text: str) -> str | None:
        if not text:
            return None
        found = set(self._sen.extract_keywords(text))
        for label in self._sen_order:
            if label in found:
                return label
        return None

    def match(self, title: str, description: str = "") -> MatchResult | None:
        title = title or ""
        if self._neg_sen.extract_keywords(title):
            return None
        if self._neg_role.extract_keywords(title):
            return None
        roles = _uniq(self._roles.extract_keywords(title))
        if not roles:
            return None
        seniority = self._seniority(title) or self._seniority(description)
        if self.require_seniority and not seniority:
            return None
        stack = _uniq(self._stack.extract_keywords(f"{title}\n{description or ''}"))
        return MatchResult(
            seniority=seniority or "Unspecified",
            matched_tech=stack or roles,
            matched_roles=roles,
        )
