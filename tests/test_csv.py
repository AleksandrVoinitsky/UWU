"""Тесты экспорта CSV (BOM и защита от формульной инъекции).

См. также: :mod:`app.web.trade`.
"""
from __future__ import annotations

from app.web.trade import _csv_response, _sanitize_csv_cell


def test_sanitize_csv_cell_neutralizes_formulas():
    assert _sanitize_csv_cell("=SUM(A1:A2)") == "'=SUM(A1:A2)"
    assert _sanitize_csv_cell("+1+2") == "'+1+2"
    assert _sanitize_csv_cell("@cmd") == "'@cmd"


def test_sanitize_csv_cell_keeps_normal_and_negative_values():
    # Обычные строки и отрицательные числа не трогаем.
    assert _sanitize_csv_cell("Обычный текст") == "Обычный текст"
    assert _sanitize_csv_cell("-100.00") == "-100.00"
    assert _sanitize_csv_cell("0.00") == "0.00"


def test_csv_response_has_bom():
    resp = _csv_response([{"a": "1", "b": "текст"}], "report.csv")
    assert resp.body.startswith("\ufeff".encode("utf-8"))
    assert "report.csv" in resp.headers["Content-Disposition"]
    assert resp.media_type == "text/csv"
