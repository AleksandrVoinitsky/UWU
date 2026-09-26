"""Простой in-process rate limiter (скользящее окно).

Используется для защиты точек входа от перебора паролей (brute-force) и спама.
Работает в рамках одного процесса — этого достаточно для текущего развёртывания
(один uvicorn-воркер). Для многопроцессного/многоворкерного режима потребуется
внешнее хранилище (Redis и т.п.).

См. также: :mod:`app.api.auth`, :mod:`app.web.auth`.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock


class SlidingWindowRateLimiter:
    """Ограничивает количество запросов по ключу за скользящее окно."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str) -> bool:
        """Регистрирует запрос и возвращает ``True``, если лимит не превышен."""
        now = time.monotonic()
        with self._lock:
            dq = self._hits[key]
            # Сбрасываем устаревшие попадания за пределами окна.
            while dq and now - dq[0] >= self.window_seconds:
                dq.popleft()
            if len(dq) >= self.max_requests:
                return False
            dq.append(now)
            return True


# Лимит попыток входа (по ключу IP + логин/телефон): не более 10 попыток в 60 с.
login_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)


def login_rate_key(request_ip: str, identifier: str) -> str:
    """Ключ лимита для входа: IP + нормализованный идентификатор."""
    return f"{request_ip}:{identifier.strip().lower()}"
