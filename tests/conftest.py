"""Shared pytest fixtures/config for the jobpipe test suite.

Per the approved plan, tests hit live ATS endpoints. To keep the suite usable
offline, live tests are tolerant (empty results never fail) and a session-scoped
`online` fixture short-circuits live tests when there is no network.
"""
from __future__ import annotations

import socket
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _has_network(host: str = "api.lever.co", port: int = 443, timeout: float = 4.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def online() -> bool:
    return _has_network()


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture()
def tmp_state_db(tmp_path) -> Path:
    return tmp_path / "state.sqlite"
