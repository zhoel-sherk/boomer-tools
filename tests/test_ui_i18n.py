"""ui_i18n: JSON language catalogs."""

from __future__ import annotations

import sys
import os

tests_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(tests_path), "src"))

from ui_i18n import UiI18n, load_catalog


def test_load_catalog_en_ru() -> None:
    en = load_catalog("en")
    ru = load_catalog("ru")
    assert en["tab.project"] == "Project"
    assert ru["tab.project"] == "Проект"


def test_ui_i18n_russian() -> None:
    i = UiI18n("ru")
    assert i.locale == "ru"
    assert i.tr("status.ready") == "Готово"


def test_unknown_locale_falls_back_en() -> None:
    i = UiI18n("xx")
    assert i.locale == "en"
