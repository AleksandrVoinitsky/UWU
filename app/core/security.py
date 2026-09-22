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
    """Создаёт JWT для пользователя (``subject`` — id пользователя)."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    """Декодирует токен и возвращает ``sub`` как ``int`` либо ``None`` при ошибке.

    Возвращает ``None`` в любом некорректном случае (неверная подпись, истёкший
    срок, нечисловой ``sub``), чтобы вызывающий код не падал с ``ValueError``.
    """
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
        return int(payload.get("sub"))
    except (jwt.PyJWTError, TypeError, ValueError):
        return None
