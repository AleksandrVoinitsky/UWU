"""Регрессионный тест: в шаблонах, переводах и исходниках нет mojibake.

Ловит классическое «двойное кодирование»: русский текст, закодированный в UTF-8,
но прочитанный как CP-1251 (например, «РћС‚РєСЂС‹С‚СЊ СЃРјРµРЅСѓ» вместо
«Открыть смену»). Такие символы не встречаются в корректном русском/английском.

См. также: :mod:`app.core.i18n`.
"""
from __future__ import annotations

from pathlib import Path

# Символы-маркеры CP-1251 mojibake: не-русская кириллица (сербские/македонские/
# украинские буквы), которая не встречается в корректном русском/английском тексте.
# Это надёжный и однозначный сигнал «двойного кодирования» (UTF-8 → CP-1251).
MOJIBAKE_SIGNATURE = "ђѓєѕіїјљњћќўџЂЃЄЅІЇЈЉЊЋЌЎЏ"

ROOT = Path(__file__).resolve().parent.parent

_EXCLUDED_PARTS = {".venv", "__pycache__", ".git", "node_modules"}


def _scan(directory: Path, suffixes: tuple[str, ...]) -> list[tuple[str, str]]:
    """Возвращает список (путь, символ) для файлов с признаками mojibake."""
    problems: list[tuple[str, str]] = []
    for path in directory.rglob("*"):
        if path.suffix not in suffixes or not path.is_file():
            continue
        if any(part in _EXCLUDED_PARTS for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        for ch in MOJIBAKE_SIGNATURE:
            if ch in text:
                problems.append((str(path.relative_to(ROOT)), ch))
    return problems


def test_no_mojibake_in_templates():
    problems = _scan(ROOT / "app" / "templates", (".html",))
    assert not problems, f"Mojibake в шаблонах: {problems}"


def test_no_mojibake_in_translations():
    problems = _scan(ROOT / "app" / "translations", (".json",))
    assert not problems, f"Mojibake в переводах: {problems}"


def test_no_mojibake_in_python_source():
    problems = _scan(ROOT / "app", (".py",))
    assert not problems, f"Mojibake в исходниках: {problems}"
