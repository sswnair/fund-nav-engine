"""Shared fixtures. The path line lets `pytest` run straight from a checkout."""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from fundnav.data import load_fund  # noqa: E402


@pytest.fixture(scope="session")
def sample():
    return load_fund()


@pytest.fixture(scope="session")
def sample_run(sample):
    from fundnav.engine import run

    return run(sample)
