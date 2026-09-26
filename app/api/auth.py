"""API аутентификации.

См. также: :mod:`app.services.auth_service`, :mod:`app.schemas.auth`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.ratelimit import login_limiter, login_rate_key
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.auth_service import AuthError, authenticate

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    ip = request.client.host if request.client else "unknown"
    if not login_limiter.hit(login_rate_key(ip, payload.login)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )
    try:
        token = await authenticate(session, payload.login, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return TokenResponse(access_token=token)
