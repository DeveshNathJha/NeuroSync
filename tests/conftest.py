"""
Shared test setup.

Every test run uses a throw-away data directory, so tests never touch the
real ~/.neurosync folder (sessions, encryption key, audit log, logs).
Must run before any `src` import, hence pytest_configure.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config):
    os.environ["NEUROSYNC_DATA_DIR"] = tempfile.mkdtemp(prefix="neurosync-test-")
