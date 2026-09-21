"""API документов: создание, проведение, отмена, журналы.

См. также: :mod:`app.services.document_service`, :mod:`app.schemas.document`.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user
from app.models.document.base_document import Document
from app.models.enums import DocSubtype, DocType
from app.models.users import User
from app.schemas.document import DocumentCreate, DocumentListOut, DocumentOut
from app.services import document_service
from app.services.stock_service import InsufficientStockError

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=list[DocumentListOut])
async def list_documents(
    doc_type: str | None = None,
    start: date | None = None,
    end: date | None = None,
    kontragent_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    stmt = select(Document).order_by(Document.date.desc(), Document.id.desc())
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if start:
        stmt = stmt.where(Document.date >= start)
    if end:
        stmt = stmt.where(Document.date <= end)
    if kontragent_id:
        stmt = stmt.where(Document.kontragent_id == kontragent_id)
    result = await session.execute(stmt)
    return list(result.scalars())


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    document = await document_service.get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def create_document(
    payload: DocumentCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if not user.has_permission("documents.write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    try:
        doc_type = DocType(payload.doc_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown doc_type") from exc
    subtype = DocSubtype(payload.subtype) if payload.subtype else None
    return await document_service.create_document(
        session,
        doc_type=doc_type,
        doc_date=payload.date,
        subtype=subtype,
        number=payload.number,
        firma_id=payload.firma_id,
        kontragent_id=payload.kontragent_id,
        dogovor_id=payload.dogovor_id,
        sklad_id=payload.sklad_id,
        sklad_to_id=payload.sklad_to_id,
        kassa_id=payload.kassa_id,
        valyuta_id=payload.valyuta_id,
        comment=payload.comment,
        extra=payload.extra,
        total=payload.total,
        items=[i.model_dump() for i in payload.items],
        created_by_id=user.id,
    )


@router.post("/{document_id}/post", response_model=DocumentOut)
async def post_document(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if not user.has_permission("documents.post"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    document = await document_service.get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    try:
        return await document_service.post_document(session, document)
    except InsufficientStockError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except document_service.DocumentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{document_id}/unpost", response_model=DocumentOut)
async def unpost_document(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if not user.has_permission("documents.post"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    document = await document_service.get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return await document_service.unpost_document(session, document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_document(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    if not user.has_permission("documents.write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    document = await document_service.get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await document_service.mark_for_deletion(session, document)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
