# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Every test runs against the synthetic "Two Town" data directory, not the bundled
Bay Area data, so the planner's rules are tested independently of any one city.

config.py reads SMARTROUTE_DATA_DIR once, at import, so it is set here before any
test module imports the planner. Tests of the bundled profile run in a subprocess.
"""
import os
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
SRC_DIR = TESTS_DIR.parent / "src"
FIXTURE_DATA_DIR = TESTS_DIR / "fixtures" / "twotown"

os.environ["SMARTROUTE_DATA_DIR"] = str(FIXTURE_DATA_DIR)
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture(autouse=True)
def _empty_cache():
    """The subscription cache is process-global; start and end every test empty."""
    from atsign import cache

    cache.clear()
    yield
    cache.clear()
