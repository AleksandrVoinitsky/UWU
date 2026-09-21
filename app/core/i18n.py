"""Интернационализация (RU / EN).

Реализована лёгким словарём, загружаемым из JSON-файлов в ``app/translations``.
Выбранный язык хранится в куки ``lang`` (по умолчанию — из настроек сервиса).
Ключи — семантические строки, значения — переводы по языкам.

См. также: :mod:`app.core.config`, :mod:`app.web.router`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "translations"
SUPPORTED_LANGUAGES = ("ru", "en")


@lru_cache
def _load(lang: str) -> dict[str, str]:
    path = TRANSLATIONS_DIR / f"{lang}.json"
    if not path.exists():
        path = TRANSLATIONS_DIR / "ru.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def translate(key: str, lang: str | None = None, **kwargs) -> str:
    """Возвращает перевод ключа; при отсутствии — сам ключ."""
    language = lang or settings.default_language
    if language not in SUPPORTED_LANGUAGES:
        language = settings.default_language
    text = _load(language).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


# Короткий алиас, удобный в шаблонах и сервисах.
t = translate
