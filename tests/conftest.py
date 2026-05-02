"""Pytest hooks: headless Qt for CI and sandboxed runs."""

from __future__ import annotations

import os

# Must run before any PySide6 import (avoids abort without a display).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
