"""Генерация PDF заказа покупателя (WeasyPrint).

WeasyPrint импортируется лениво — на платформах без GTK (например, Windows dev)
сам сервис остаётся импортируемым, а PDF генерируется в Docker (Linux), где
системные библиотеки установлены.

См. также: :mod:`app.templates`, ``app/templates/customer/order_pdf.html``.
"""
from __future__ import annotations

from app.templates import render


def render_order_html(order: dict) -> str:
    """Рендерит HTML печатной формы заказа (для отладки/тестов)."""
    return render("customer/order_pdf.html", order=order)


def render_order_pdf(order: dict) -> bytes:
    """Генерирует PDF заказа (WeasyPrint)."""
    from weasyprint import HTML  # ленивый импорт (зависит от системных библиотек)

    html = render_order_html(order)
    return HTML(string=html, base_url=".").write_pdf()
