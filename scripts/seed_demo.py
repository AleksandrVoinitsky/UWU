"""Наполнение БД реалистичными демо-данными (товары, контрагенты, документы).

Запуск:
  $env:DATABASE_URL="postgresql+asyncpg://uwu:uwu@localhost:5433/uwu"
  python scripts/seed_demo.py

Создаёт: номенклатуру с ценами, контрагентов, склады, кассу, фирму, приходные и
расходные накладные, денежные документы — для проверки отчётов, пагинации, ABC.
"""
from __future__ import annotations

import asyncio
import os
import random
from datetime import date, timedelta
from decimal import Decimal

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://uwu:uwu@localhost:5433/uwu")

from app.core.database import async_session_factory  # noqa: E402
from app.models import catalog as cat  # noqa: E402
from app.models.enums import DocSubtype, DocType  # noqa: E402
from app.services import catalog_service, document_service  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

# (наименование, закупочная, розничная)
NOMENKLATURA = [
    ("Молоко пастеризованное 3,2% 1 л", 58, 78),
    ("Хлеб пшеничный нарезной", 32, 45),
    ("Сыр Российский 200 г", 140, 189),
    ("Масло сливочное 82,5% 180 г", 165, 219),
    ("Кофе растворимый 100 г", 280, 369),
    ("Чай чёрный листовой 100 пак.", 210, 279),
    ("Сахар-песок 1 кг", 62, 84),
    ("Мука пшеничная в/с 2 кг", 95, 128),
    ("Рис круглозёрный 800 г", 78, 105),
    ("Макароны спагетти 450 г", 54, 72),
    ("Яйца куриные С0 10 шт", 92, 118),
    ("Курица охлаждённая 1,2 кг", 240, 315),
    ("Говядина мякоть 1 кг", 520, 649),
    ("Свинина окорок 1 кг", 330, 429),
    ("Форель радужная 400 г", 380, 499),
    ("Огурцы свежие 1 кг", 85, 120),
    ("Помидоры свежие 1 кг", 120, 165),
    ("Картофель 1 кг", 35, 52),
    ("Яблоки Гала 1 кг", 95, 135),
    ("Бананы 1 кг", 88, 119),
    ("Сок апельсиновый 1 л", 105, 145),
    ("Вода минеральная 1,5 л", 42, 65),
    ("Шоколад молочный 90 г", 75, 99),
    ("Печенье овсяное 250 г", 68, 92),
    ("Стиральный порошок 450 г", 145, 189),
]

KONTRAGENTY = [
    "ООО Продснаб",
    "АО Молокозавод",
    "ИП Смирнов А.В.",
    "ООО Торговый дом «Меркурий»",
    "ЗАО Агротрейд",
    "ООО Розничная сеть №1",
]


async def main() -> None:
    random.seed(42)
    async with async_session_factory() as session:
        # Склады
        sklady = []
        for code, name in (("01", "Основной склад"), ("02", "Розничный магазин")):
            existing = await catalog_service.list_all(session, cat.Sklad)
            if not any(s.code == code for s in existing):
                sklady.append(await catalog_service.create_one(session, cat.Sklad, code=code, name=name, tip="optovy"))
            else:
                sklady.append(next(s for s in existing if s.code == code))

        # Касса и фирма
        if not await catalog_service.list_all(session, cat.Kassa):
            await catalog_service.create_one(session, cat.Kassa, name="Касса №1")
        if not await catalog_service.list_all(session, cat.Firma):
            await catalog_service.create_one(session, cat.Firma, name="ООО Универсал Трейд", inn="7712345678")

        # Типы цен
        tipy = await catalog_service.list_all(session, cat.TipTsen)
        if not tipy:
            await catalog_service.create_one(session, cat.TipTsen, name="Розничная", markup_percent=Decimal("35"))
            await catalog_service.create_one(session, cat.TipTsen, name="Оптовая", markup_percent=Decimal("15"))

        # Номенклатура
        nomen = await catalog_service.list_all(session, cat.Nomenklatura)
        if not nomen:
            for name, pur, ret in NOMENKLATURA:
                code = await catalog_service.next_nomenklatura_code(session)
                await catalog_service.create_one(
                    session, cat.Nomenklatura, code=code, name=name, vid="tovar",
                    purchase_price=Decimal(pur), retail_price=Decimal(ret),
                )
            nomen = await catalog_service.list_all(session, cat.Nomenklatura)

        # Контрагенты
        kontragenty = await catalog_service.list_all(session, cat.Kontragent)
        if not kontragenty:
            for name in KONTRAGENTY:
                code = await catalog_service.next_kontragent_code(session)
                await catalog_service.create_one(session, cat.Kontragent, code=code, name=name, inn=str(random.randint(7700000000, 7799999999)))
            kontragenty = await catalog_service.list_all(session, cat.Kontragent)

        # Чаты мессенджера (клиенты + боты).
        from app.models.messaging import Chat, Message
        chat_count = (await session.execute(select(func.count(Chat.id)))).scalar()
        if not chat_count:
            for kg in kontragenty[:3]:
                chat = Chat(name=kg.name, channel="client", kontragent_id=kg.id)
                session.add(chat)
                await session.flush()
                session.add(Message(chat_id=chat.id, direction="in", text="Здравствуйте! Интересует наличие товара на складе."))
            maks = Chat(name="Макс (бот)", channel="maks")
            session.add(maks)
            await session.flush()
            session.add(Message(chat_id=maks.id, direction="in", text="Привет! Я бот Макс — помогу с заказами и статусами."))
            tg = Chat(name="Telegram (бот)", channel="telegram")
            session.add(tg)
            await session.flush()
            session.add(Message(chat_id=tg.id, direction="in", text="Подключение к Telegram настраивается."))
            await session.commit()

        # Проверяем, есть ли уже документы (идемпотентность).
        from app.models.document.base_document import Document
        count = (await session.execute(select(func.count(Document.id)))).scalar()
        if count:
            print(f"Документов уже: {count}. Пропуск наполнения.")
            return

        today = date.today()
        main_sklad = sklady[0].id

        # Контроль остатков отключаем на время наполнения (массовая загрузка).
        await catalog_service.set_constant(session, "restock_control", "none")

        # Приходные накладные — оприходуем все товары (по 4 позиции в документе).
        for i in range(0, len(nomen), 4):
            chunk = nomen[i : i + 4]
            items = [
                {
                    "nomenklatura_id": n.id,
                    "quantity": Decimal(random.randint(300, 600)),
                    "price": n.purchase_price or Decimal("50"),
                }
                for n in chunk
            ]
            doc = await document_service.create_document(
                session, doc_type=DocType.PRIHOD, subtype=DocSubtype.CREDIT,
                doc_date=today - timedelta(days=30 - i),
                sklad_id=main_sklad,
                kontragent_id=random.choice(kontragenty[:3]).id, items=items,
            )
            await document_service.post_document(session, doc)

        # Расходные накладные (продажи) — случайные позиции малыми партиями.
        for d in range(28, 0, -2):
            doc_date = today - timedelta(days=d)
            items = []
            for _ in range(random.randint(1, 5)):
                n = random.choice(nomen)
                items.append({
                    "nomenklatura_id": n.id,
                    "quantity": Decimal(random.randint(1, 8)),
                    "price": n.retail_price or n.purchase_price or Decimal("100"),
                })
            doc = await document_service.create_document(
                session, doc_type=DocType.RASHOD, subtype=DocSubtype.CASH,
                doc_date=doc_date, sklad_id=main_sklad, items=items,
            )
            await document_service.post_document(session, doc)

        # Несколько ПКО (приход наличных от покупателей).
        for d in range(10, 0, -4):
            doc = await document_service.create_document(
                session, doc_type=DocType.PRIHODNY_KASSOVY_ORDER,
                doc_date=today - timedelta(days=d),
                kontragent_id=random.choice(kontragenty[3:]).id,
                total=Decimal(random.randint(5000, 40000)),
            )
            await document_service.post_document(session, doc)

        print("Демо-данные созданы:", len(nomen), "товаров,", len(kontragenty), "контрагентов")


if __name__ == "__main__":
    asyncio.run(main())
