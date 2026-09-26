"""Общее сохранение загружаемых изображений.

Поддерживает PNG/JPEG/GIF/WebP. WebP — основной формат «стикеров» в
мессенджерах (с альфа-каналом/прозрачностью): файл пишется как есть, без
перекодирования, поэтому прозрачный фон сохраняется.

См. также: :mod:`app.web.trade`, :mod:`app.web.site_admin`.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings

MAX_IMAGE_BYTES = 5 * 1024 * 1024

# Точные сигнатуры по первым байтам (WebP — RIFF....WEBP, чтобы отличить от WAV).
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF8", ".gif"),
)


def _detect_webp(data: bytes) -> bool:
    return data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP"


def detect_ext(data: bytes) -> str | None:
    """Определяет расширение изображения по сигнатуре (None, если не изображение)."""
    for sig, ext in _SIGNATURES:
        if data.startswith(sig):
            return ext
    if _detect_webp(data):
        return ".webp"
    return None


async def save_image(file: UploadFile, prefix: str) -> str | None:
    """Валидирует и сохраняет изображение; возвращает имя файла или None.

    Прозрачность сохраняется: байты пишутся без изменений.
    """
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        return None
    ext = detect_ext(data)
    if ext is None:
        return None
    uploads = Path(settings.uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex[:8]}{ext}"
    (uploads / filename).write_bytes(data)
    return filename
