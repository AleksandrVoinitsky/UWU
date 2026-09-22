"""Агрегирующий роутер REST API."""
from fastapi import APIRouter

from app.api import auth, catalog, documents, messaging, reports, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(catalog.router)
api_router.include_router(documents.router)
api_router.include_router(reports.router)
api_router.include_router(messaging.router)
