"""MiniApp: аутентификация по initData мессенджера и привязка к покупателю.

Пользователь мессенджера (Telegram/MAX) идентифицируется по подписанному
``initData``, проверяется подпись и связывается с учётной записью покупателя
через :class:`app.models.customer.CustomerBinding`. При первом входе покупатель
создаётся автоматически (синтетический логин; привязку к реальному телефону/
контрагенту добавим на этапе SMS-верификации).

См. также: :mod:`app.models.customer`, :mod:`app.customer.miniapp`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.customer import Customer, CustomerBinding
from app.services import customer_service

logger = get_logger("app.miniapp")

CHANNEL_TELEGRAM = "telegram"
CHANNEL_MAKS = "maks"


def _telegram_secret(bot_token: str) -> bytes:
    """Секрет подписи Telegram: HMAC_SHA256(bot_token, "WebAppData")."""
    return hmac.new(bot_token.encode(), b"WebAppData", hashlib.sha256).digest()


def _sign(data: str, key: bytes) -> str:
    return hmac.new(key, data.encode(), hashlib.sha256).hexdigest()


def validate_init_data(channel: str, init_data: str, secret: str) -> dict | None:
    """Проверяет подпись initData и возвращает ``{channel, external_id, name}``.

    Возвращает ``None`` при неверной подписи или неполных данных.

    Подпись считается по **сырым** (URL-encoded) парам ``key=value``, как их
    отправляет мессенджер; значения декодируются только для извлечения данных
    (иначе пересчитанный HMAC никогда не совпадёт с присланным ``hash``).
    """
    raw: dict[str, str] = {}
    for part in init_data.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            raw[k] = v
    decoded = {k: urllib.parse.unquote_plus(v) for k, v in raw.items()}

    if channel == CHANNEL_TELEGRAM:
        provided = raw.get("hash")
        try:
            user = json.loads(decoded.get("user", "{}"))
        except json.JSONDecodeError:
            return None
        external_id = str(user.get("id") or "")
        if not external_id or not provided:
            return None
        check = "\n".join(f"{k}={v}" for k, v in sorted(raw.items()) if k != "hash")
        if not hmac.compare_digest(_sign(check, _telegram_secret(secret)), provided):
            return None
        name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")]))
        return {"channel": channel, "external_id": external_id, "name": name}

    if channel == CHANNEL_MAKS:
        provided = raw.get("sign")
        external_id = raw.get("vk_user_id") or ""
        if not external_id or not provided:
            return None
        check = "&".join(f"{k}={v}" for k, v in sorted(raw.items()) if k != "sign")
        if not hmac.compare_digest(_sign(check, secret.encode()), provided):
            return None
        return {"channel": channel, "external_id": external_id, "name": ""}

    return None


def make_test_init_data(channel: str, secret: str, user_id: int, name: str = "Тест") -> str:
    """Собирает валидный initData (для тестов и локальной проверки).

    Подпись формируется по URL-encoded значениям — так же, как это делает
    мессенджер, — чтобы тесты совпадали с реальным алгоритмом проверки.
    """
    if channel == CHANNEL_TELEGRAM:
        user = json.dumps({"id": user_id, "first_name": name}, ensure_ascii=False)
        params = {"user": user, "auth_date": "1700000000", "query_id": "1"}
        encoded = urllib.parse.urlencode(params)
        raw = dict(s.split("=", 1) for s in encoded.split("&"))
        check = "\n".join(f"{k}={v}" for k, v in sorted(raw.items()))
        params["hash"] = _sign(check, _telegram_secret(secret))
        return urllib.parse.urlencode(params)

    params = {"vk_user_id": str(user_id), "vk_app_id": "1", "vk_ts": "1700000000"}
    encoded = urllib.parse.urlencode(params)
    raw = dict(s.split("=", 1) for s in encoded.split("&"))
    check = "&".join(f"{k}={v}" for k, v in sorted(raw.items()))
    params["sign"] = _sign(check, secret.encode())
    return urllib.parse.urlencode(params)


async def get_binding(
    session: AsyncSession, channel: str, external_id: str
) -> CustomerBinding | None:
    stmt = select(CustomerBinding).where(
        CustomerBinding.channel == channel, CustomerBinding.external_id == external_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def find_or_create_customer(
    session: AsyncSession, channel: str, external_id: str, name: str
) -> Customer:
    """Возвращает покупателя по привязке или создаёт нового (авто-линк)."""
    binding = await get_binding(session, channel, external_id)
    if binding is not None:
        customer = await session.get(Customer, binding.customer_id)
        if customer is not None:
            return customer

    synthetic_phone = f"ma_{channel}_{external_id}"
    customer = await customer_service.get_customer_by_phone(session, synthetic_phone)
    if customer is None:
        # Пароль не задаётся: вход только через привязку мессенджера.
        customer = Customer(phone=synthetic_phone, password_hash="", name=name or None)
        session.add(customer)
        await session.flush()
    session.add(CustomerBinding(channel=channel, external_id=external_id, customer_id=customer.id))
    await session.commit()
    await session.refresh(customer)
    logger.info("MiniApp: привязан %s/%s к покупателю #%s", channel, external_id, customer.id)
    return customer
