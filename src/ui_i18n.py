"""Load UI strings from ``boomer/lang/<locale>.json`` (fallback: English)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FALLBACK_LOCALE = "en"
_SUPPORTED = frozenset({"en", "ru"})


def lang_directory() -> Path:
    """``boomer/lang`` next to ``boomer/src``."""
    return Path(__file__).resolve().parent.parent / "lang"


def load_catalog(locale: str) -> dict[str, Any]:
    loc = locale if locale in _SUPPORTED else _FALLBACK_LOCALE
    path = lang_directory() / f"{loc}.json"
    if not path.is_file():
        path = lang_directory() / f"{_FALLBACK_LOCALE}.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


class UiI18n:
    """Simple JSON-based UI translator."""

    def __init__(self, locale: str = _FALLBACK_LOCALE) -> None:
        self.locale = locale if locale in _SUPPORTED else _FALLBACK_LOCALE
        self._strings = load_catalog(self.locale)
        self._fallback = load_catalog(_FALLBACK_LOCALE)

    def set_locale(self, locale: str) -> None:
        self.locale = locale if locale in _SUPPORTED else _FALLBACK_LOCALE
        self._strings = load_catalog(self.locale)

    def tr(self, key: str, **kwargs: Any) -> str:
        raw = self._strings.get(key)
        if raw is None:
            raw = self._fallback.get(key, key)
        s = raw if isinstance(raw, str) else str(raw)
        if kwargs:
            try:
                return s.format(**kwargs)
            except (KeyError, ValueError):
                return s
        return s
