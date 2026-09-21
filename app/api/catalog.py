"""API справочников (НСИ).

См. также: :mod:`app.models.catalog`, :mod:`app.services.catalog_service`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user
from app.models import catalog as cat
from app.models.users import User
from app.schemas import catalog as schemas
from app.services import catalog_service

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/valyuty", response_model=list[schemas.ValyutaOut])
async def list_valyuty(session: AsyncSession = Depends(get_session)):
    return await catalog_service.list_all(session, cat.Valyuta)


@router.post("/valyuty", response_model=schemas.ValyutaOut, status_code=status.HTTP_201_CREATED)
async def create_valyuta(payload: schemas.ValyutaCreate, session: AsyncSession = Depends(get_session)):
    return await catalog_service.create_one(session, cat.Valyuta, **payload.model_dump())


@router.get("/stavki_nds", response_model=list[schemas.StavkaNDSOut])
async def list_stavki_nds(session: AsyncSession = Depends(get_session)):
    return await catalog_service.list_all(session, cat.StavkaNDS)


@router.post("/stavki_nds", response_model=schemas.StavkaNDSOut, status_code=status.HTTP_201_CREATED)
async def create_stavka_nds(payload: schemas.StavkaNDSBase, session: AsyncSession = Depends(get_session)):
    return await catalog_service.create_one(session, cat.StavkaNDS, **payload.model_dump())


@router.get("/edinitsy", response_model=list[schemas.EdinitsaOut])
async def list_edinitsy(session: AsyncSession = Depends(get_session)):
    return await catalog_service.list_all(session, cat.Edinitsa)


@router.post("/edinitsy", response_model=schemas.EdinitsaOut, status_code=status.HTTP_201_CREATED)
async def create_edinitsa(payload: schemas.EdinitsaBase, session: AsyncSession = Depends(get_session)):
    return await catalog_service.create_one(session, cat.Edinitsa, **payload.model_dump())


@router.get("/firmy", response_model=list[schemas.FirmaOut])
async def list_firmy(session: AsyncSession = Depends(get_session)):
    return await catalog_service.list_all(session, cat.Firma)


@router.post("/firmy", response_model=schemas.FirmaOut, status_code=status.HTTP_201_CREATED)
async def create_firma(payload: schemas.FirmaBase, session: AsyncSession = Depends(get_session)):
    return await catalog_service.create_one(session, cat.Firma, **payload.model_dump())


@router.get("/sklady", response_model=list[schemas.SkladOut])
async def list_sklady(session: AsyncSession = Depends(get_session)):
    return await catalog_service.list_all(session, cat.Sklad)


@router.post("/sklady", response_model=schemas.SkladOut, status_code=status.HTTP_201_CREATED)
async def create_sklad(payload: schemas.SkladBase, session: AsyncSession = Depends(get_session)):
    return await catalog_service.create_one(session, cat.Sklad, **payload.model_dump())


@router.get("/kassy", response_model=list[schemas.KassaOut])
async def list_kassy(session: AsyncSession = Depends(get_session)):
    return await catalog_service.list_all(session, cat.Kassa)


@router.post("/kassy", response_model=schemas.KassaOut, status_code=status.HTTP_201_CREATED)
async def create_kassa(payload: schemas.KassaBase, session: AsyncSession = Depends(get_session)):
    return await catalog_service.create_one(session, cat.Kassa, **payload.model_dump())


@router.get("/kontragenty", response_model=list[schemas.KontragentOut])
async def list_kontragenty(session: AsyncSession = Depends(get_session)):
    return await catalog_service.list_all(session, cat.Kontragent)


@router.post("/kontragenty", response_model=schemas.KontragentOut, status_code=status.HTTP_201_CREATED)
async def create_kontragent(payload: schemas.KontragentBase, session: AsyncSession = Depends(get_session)):
    if not payload.code:
        payload.code = await catalog_service.next_kontragent_code(session)
    return await catalog_service.create_one(session, cat.Kontragent, **payload.model_dump())


@router.get("/dogovory", response_model=list[schemas.DogovorOut])
async def list_dogovory(session: AsyncSession = Depends(get_session)):
    return await catalog_service.list_all(session, cat.Dogovor)


@router.post("/dogovory", response_model=schemas.DogovorOut, status_code=status.HTTP_201_CREATED)
async def create_dogovor(payload: schemas.DogovorBase, session: AsyncSession = Depends(get_session)):
    return await catalog_service.create_one(session, cat.Dogovor, **payload.model_dump())


@router.get("/nomenklatura", response_model=list[schemas.NomenklaturaOut])
async def list_nomenklatura(session: AsyncSession = Depends(get_session)):
    return await catalog_service.list_all(session, cat.Nomenklatura)


@router.post("/nomenklatura", response_model=schemas.NomenklaturaOut, status_code=status.HTTP_201_CREATED)
async def create_nomenklatura(payload: schemas.NomenklaturaBase, session: AsyncSession = Depends(get_session)):
    if not payload.code:
        payload.code = await catalog_service.next_nomenklatura_code(session)
    return await catalog_service.create_one(session, cat.Nomenklatura, **payload.model_dump())


@router.get("/tipy_tsen", response_model=list[schemas.TipTsenOut])
async def list_tipy_tsen(session: AsyncSession = Depends(get_session)):
    return await catalog_service.list_all(session, cat.TipTsen)


@router.post("/tipy_tsen", response_model=schemas.TipTsenOut, status_code=status.HTTP_201_CREATED)
async def create_tip_tsen(payload: schemas.TipTsenBase, session: AsyncSession = Depends(get_session)):
    return await catalog_service.create_one(session, cat.TipTsen, **payload.model_dump())


# --- Константы ---


@router.get("/constants")
async def get_constants(session: AsyncSession = Depends(get_session)):
    return await catalog_service.get_constants(session)


@router.put("/constants/{key}")
async def set_constant(
    key: str,
    value: dict,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if not user.has_permission("service.settings"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    await catalog_service.set_constant(session, key, value.get("value"))
    return {"key": key, "value": value.get("value")}
