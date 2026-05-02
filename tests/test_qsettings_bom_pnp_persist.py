"""QSettings round-trip for per-file BOM / PnP tab keys (requires PySide6)."""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings

from settings_paths import path_settings_hash


def test_bom_ui_settings_roundtrip() -> None:
    org = f"BoomerTest_{uuid.uuid4().hex[:12]}"
    app_name = "Roundtrip"
    s = QSettings(org, app_name)
    path = "/tmp/example_bom_for_settings.csv"
    h = path_settings_hash(path)
    g = f"bom/ui/{h}"
    s.beginGroup(g)
    s.setValue("separator", ";")
    s.setValue("has_headers", False)
    s.setValue("first_row", "2")
    s.setValue("last_row", "99")
    s.setValue("mappings", ["REF", "Comment", "-"])
    s.endGroup()
    s.sync()

    s2 = QSettings(org, app_name)
    s2.beginGroup(g)
    assert str(s2.value("separator")) == ";"
    assert s2.value("has_headers") in (False, "false", 0, "0")
    assert str(s2.value("first_row")) == "2"
    assert str(s2.value("last_row")) == "99"
    m = s2.value("mappings")
    assert isinstance(m, list)
    assert list(m) == ["REF", "Comment", "-"]
    s2.endGroup()
