"""Управление пользователями и ролями (доступно администратору).

См. также: :mod:`app.models.users`, :mod:`app.core.security`.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.enums import RoleKey
from app.models.users import DEFAULT_ROLE_PERMISSIONS, Role, User


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.id))
    return list(result.scalars())


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def create_user(
    session: AsyncSession,
    login: str,
    password: str,
    *,
    email: str | None = None,
    full_name: str | None = None,
    is_active: bool = True,
    is_admin: bool = False,
    language: str = "ru",
    role_id: int | None = None,
) -> User:
    user = User(
        login=login,
        password_hash=hash_password(password),
        email=email,
        full_name=full_name,
        is_active=is_active,
        is_admin=is_admin,
        language=language,
        role_id=role_id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user(
    session: AsyncSession,
    user: User,
    *,
    password: str | None = None,
    email: str | None = None,
    full_name: str | None = None,
    is_active: bool | None = None,
    is_admin: bool | None = None,
    language: str | None = None,
    role_id: int | None = None,
) -> User:
    if password is not None:
        user.password_hash = hash_password(password)
    if email is not None:
        user.email = email
    if full_name is not None:
        user.full_name = full_name
    if is_active is not None:
        user.is_active = is_active
    if is_admin is not None:
        user.is_admin = is_admin
    if language is not None:
        user.language = language
    if role_id is not None:
        user.role_id = role_id
    await session.commit()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user: User) -> None:
    await session.delete(user)
    await session.commit()


async def list_roles(session: AsyncSession) -> list[Role]:
    result = await session.execute(select(Role).order_by(Role.id))
    return list(result.scalars())


async def get_role(session: AsyncSession, role_id: int) -> Role | None:
    return await session.get(Role, role_id)


async def create_role(
    session: AsyncSession, key: str, name: str, permissions: list[str]
) -> Role:
    role = Role(key=key, name=name, permissions=permissions)
    session.add(role)
    await session.commit()
    await session.refresh(role)
    return role


async def update_role(
    session: AsyncSession, role: Role, name: str | None, permissions: list[str] | None
) -> Role:
    if name is not None:
        role.name = name
    if permissions is not None:
        role.permissions = permissions
    await session.commit()
    await session.refresh(role)
    return role


async def seed_default_roles(session: AsyncSession) -> None:
    """Создаёт встроенные роли, если их нет."""
    existing = {r.key for r in await list_roles(session)}
    for rkey, perms in DEFAULT_ROLE_PERMISSIONS.items():
        if rkey.value not in existing:
            session.add(
                Role(key=rkey.value, name=rkey.value.capitalize(), permissions=perms)
            )
    await session.commit()
