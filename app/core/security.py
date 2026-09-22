"""Безопасность: хеширование паролей и JWT-токены.

Пароли хешируются ``bcrypt`` (соль встроена в хеш). Токены — ``PyJWT`` (HS256),
срок жизни задаётся в :class:`app.core.config.Settings`.

См. также: :mod:`app.models.users`, :mod:`app.services.auth_service`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("app.security")

# Известные небезопасные значения по умолчанию (попадающие в .env.example и
# docker-compose). Их использование в проде допустимо только с явным
# предупреждением оператора.
_INSECURE_SECRETS = {
    "",
    "change-me",
    "change-me-to-a-long-random-string",
    "secret",
    "changeme",
}
_WEAK_ADMIN_PASSWORDS = {"", "admin", "password", "123456", "changeme"}


def validate_security_settings() -> list[str]:
    """Проверяет настройки безопасности и возвращает список предупреждений.

    Не падает с ошибкой — чтобы не ломать существующие развёртывания, — но
    громко логирует проблемы, которые оператор обязан устранить в проде.

    См. также: :class:`app.core.config.Settings`.
    """
    warnings: list[str] = []
    if settings.secret_key in _INSECURE_SECRETS or len(settings.secret_key) < 16:
        warnings.append(
            "SECRET_KEY использует небезопасное значение по умолчанию или слишком "
            "короткий. Задайте длинный случайный SECRET_KEY в переменных окружения."
        )
    if settings.admin_password in _WEAK_ADMIN_PASSWORDS:
        warnings.append(
            "ADMIN_PASSWORD использует слабый пароль по умолчанию. Смените его."
        )
    for message in warnings:
        logger.warning("Security check: %s", message)
    return warnings


def hash_password(password: str) -> str:
    """Возвращает bcrypt-хеш пароля."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Проверяет пароль на соответствие хешу."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """Создаёт JWT для пользователя-сотрудника (``subject`` — id пользователя).

    В payload добавляется ``type="user"``, чтобы токены сотрудников и
    покупателей не могли использоваться взаимозаменяемо.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {
        "sub": subject,
        "type": "user",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_customer_token(customer_id: int, expires_minutes: int | None = None) -> str:
    """Создаёт JWT для покупателя (``customer_id``) с ``type="customer"``."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {
        "sub": str(customer_id),
        "type": "customer",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _decode(token: str) -> dict | None:
    """Декодирует JWT без проверки типа субъекта."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None


def decode_access_token(token: str) -> int | None:
    """Декодирует токен сотрудника и возвращает ``sub`` как ``int``.

    Возвращает ``None`` в любом некорректном случае (неверная подпись, истёкший
    срок, нечисловой ``sub``) или если токен не помечен ``type="user"`` — это
    не даёт токену покупателя аутентифицироваться как сотрудник.
    """
    payload = _decode(token)
    if payload is None or payload.get("type") != "user":
        return None
    try:
        return int(payload.get("sub"))
    except (TypeError, ValueError):
        return None


def decode_customer_token(token: str) -> int | None:
    """Декодирует токен покупателя (``type="customer"``) и возвращает id."""
    payload = _decode(token)
    if payload is None or payload.get("type") != "customer":
        return None
    try:
        return int(payload.get("sub"))
    except (TypeError, ValueError):
        return None
