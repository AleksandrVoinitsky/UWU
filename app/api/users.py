"""API управления пользователями и ролями (только администратор).

См. также: :mod:`app.services.user_service`, :mod:`app.models.users`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import require_admin
from app.models.users import PERMISSIONS, User
from app.schemas.auth import (
    PermissionOut,
    RoleCreate,
    RoleOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services import user_service
from app.services.auth_service import get_user_by_login

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserOut])
async def list_users(session: AsyncSession = Depends(get_session)) -> list[User]:
    return await user_service.list_users(session)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, session: AsyncSession = Depends(get_session)) -> User:
    existing = await get_user_by_login(session, payload.login)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Login already exists")
    return await user_service.create_user(session, **payload.model_dump())


# --- Роли и права (статичные пути должны быть объявлены до /{user_id}) ---


@router.get("/roles/list", response_model=list[RoleOut])
async def list_roles(session: AsyncSession = Depends(get_session)) -> list:
    return await user_service.list_roles(session)


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
async def create_role(payload: RoleCreate, session: AsyncSession = Depends(get_session)):
    return await user_service.create_role(session, payload.key, payload.name, payload.permissions)


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions() -> list[PermissionOut]:
    return [PermissionOut(key=k, description=v) for k, v in PERMISSIONS.items()]


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, session: AsyncSession = Depends(get_session)) -> User:
    user = await user_service.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int, payload: UserUpdate, session: AsyncSession = Depends(get_session)
) -> User:
    user = await user_service.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return await user_service.update_user(
        session, user, **payload.model_dump(exclude_unset=True)
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_user(user_id: int, session: AsyncSession = Depends(get_session)) -> Response:
    user = await user_service.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.is_admin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete admin")
    await user_service.delete_user(session, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
