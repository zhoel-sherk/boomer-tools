"""Tests for working_copy_ui (requires PySide6)."""

from __future__ import annotations

import tempfile

import pytest

pytest.importorskip("PySide6")

from PySide6 import QtWidgets

from working_copy_ui import prompt_recover_snapshot


def test_prompt_recover_no_snapshot_returns_none() -> None:
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    with tempfile.TemporaryDirectory() as td:
        out = prompt_recover_snapshot(None, "/nonexistent/path/file.csv", "bom", td)
    assert out is None
