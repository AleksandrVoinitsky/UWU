"""Вспомогательные утилиты веб-интерфейса (JSON/CSV-безопасность).

Вынесены из ``app.web.trade`` для переиспользования и тестируемости.

См. также: :mod:`app.web.trade`.
"""
from __future__ import annotations

import csv
import io
import json

from fastapi.responses import Response


# Символы, с которых Excel/Google Sheets трактуют ячейку как формулу.
# Экранируем их, чтобы пользовательские данные не превращались в формулы
# (CSV/формульная инъекция). Минус не экранируем — отрицательные суммы легитимны.
_CSV_FORMULA_PREFIXES = ("=", "+", "@", "\t", "\r")


def _json_safe(obj) -> str:
    """Сериализует объект в JSON, безопасный для встраивания в ``<script>``.

    ``json.dumps`` не экранирует ``<``/``>``/``&``, поэтому строка вида
    ``</script><script>…`` может разорвать script-контекст (stored XSS).
    Экранирование этих символов в ``\\uXXXX`` нейтрализует атаку, сохраняя
    валидный JSON. Используется вместе с ``| safe`` в шаблонах.
    """
    return (
        json.dumps(obj, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _sanitize_csv_cell(value: object) -> str:
    """Экранирует значение ячейки CSV от формульной инъекции."""
    text = str(value)
    stripped = text.lstrip()
    if stripped.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


def _csv_response(rows: list[dict], filename: str) -> Response:
    """Формирует CSV-ответ для экспорта отчёта (с UTF-8 BOM для Excel)."""
    output = io.StringIO()
    output.write("\ufeff")  # BOM: корректная кириллица при открытии в Excel.
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow({k: _sanitize_csv_cell(v) for k, v in r.items()})
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
