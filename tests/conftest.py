"""Shared pytest configuration for the whole project."""

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Repository root: the parent of ``tests/`` (``/app`` inside the containers)."""
    return Path(__file__).resolve().parent.parent


def _integration_enabled() -> bool:
    """Integration tests compile and run C++, so they only run where that is safe.

    That is the ``sandbox`` service (root, with a ``/sandbox`` tmpfs) or when explicitly
    enabled with ``SANDBOX_INTEGRATION=1``.
    """
    if os.environ.get("SANDBOX_INTEGRATION") == "1":
        return True
    return os.geteuid() == 0 and Path("/sandbox").is_dir()


def pytest_collection_modifyitems(config, items):
    if _integration_enabled():
        return
    skip = pytest.mark.skip(
        reason="integration test: runs only in the sandbox service (or SANDBOX_INTEGRATION=1)"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
