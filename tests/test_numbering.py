"""Тесты нумерации документов.

См. также: :mod:`app.services.document_service`.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete

from app.models.document.base_document import Document
from app.models.enums import DocType
from app.services import document_service


async def test_next_document_number_no_duplicates_after_delete(seeded_session):
    """Номер считается от максимума: после удаления документа дублей не возникает."""
    d1 = await document_service.create_document(
        seeded_session, doc_type=DocType.PRIHOD, doc_date=date.today()
    )
    d2 = await document_service.create_document(
        seeded_session, doc_type=DocType.PRIHOD, doc_date=date.today()
    )
    d3 = await document_service.create_document(
        seeded_session, doc_type=DocType.PRIHOD, doc_date=date.today()
    )
    n3 = d3.number

    # Жёстко удаляем средний документ.
    await seeded_session.execute(delete(Document).where(Document.id == d2.id))
    await seeded_session.commit()

    d4 = await document_service.create_document(
        seeded_session, doc_type=DocType.PRIHOD, doc_date=date.today()
    )
    # Новый номер не должен совпадать с уже существующим d3.
    assert d4.number != n3
    assert int(d4.number.rsplit("-", 1)[1]) > int(n3.rsplit("-", 1)[1])


async def test_document_numbers_are_sequential(seeded_session):
    """Номера идут последовательно с префиксом вида документа."""
    d1 = await document_service.create_document(
        seeded_session, doc_type=DocType.PRIHOD, doc_date=date.today()
    )
    d2 = await document_service.create_document(
        seeded_session, doc_type=DocType.PRIHOD, doc_date=date.today()
    )
    assert d1.number.startswith("PR-")
    assert int(d2.number.rsplit("-", 1)[1]) == int(d1.number.rsplit("-", 1)[1]) + 1
