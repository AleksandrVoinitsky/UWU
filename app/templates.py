"""Настройка Jinja2 и рендеринг шаблонов.

См. также: :mod:`app.core.i18n`.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.i18n import translate
from app.web.icons import icon

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    enable_async=False,
)

# Глобальные функции в шаблонах: перевод и inline-SVG иконки.
_env.globals["t"] = translate
_env.globals["icon"] = icon


def render(template_name: str, **context) -> str:
    """Рендерит шаблон в строку."""
    return _env.get_template(template_name).render(**context)
