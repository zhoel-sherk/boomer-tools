"""Tests for stable path hashing used in QSettings keys."""

from __future__ import annotations

from pathlib import Path

from settings_paths import path_settings_hash


def test_path_settings_hash_stable() -> None:
    a = path_settings_hash("/tmp/foo/bar.csv")
    b = path_settings_hash(Path("/tmp/foo/bar.csv"))
    assert a == b
    assert len(a) == 16


def test_path_settings_hash_different_paths() -> None:
    assert path_settings_hash("/a/x") != path_settings_hash("/a/y")
