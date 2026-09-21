# Развёртывание (Docker)

## Состав

`docker-compose.yml` поднимает два сервиса:

1. **db** — PostgreSQL 16 (alpine), том `pgdata` для данных.
2. **app** — UWU (FastAPI + uvicorn), порт 8000.

## Переменные окружения

Задаются в `.env` (см. `.env.example`):

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://uwu:uwu@db:5432/uwu` | Строка подключения |
| `ADMIN_LOGIN` | `admin` | Логин администратора |
| `ADMIN_PASSWORD` | `admin` | Пароль администратора |
| `ADMIN_EMAIL` | `admin@uwu.local` | Email администратора |
| `SECRET_KEY` | `change-me-...` | Ключ подписи JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | Срок жизни токена |
| `DEFAULT_CURRENCY` | `RUB` | Валюта по умолчанию |
| `DEFAULT_LANGUAGE` | `ru` | Язык интерфейса по умолчанию |

## Запуск

```bash
cp .env.example .env
# отредактировать ADMIN_PASSWORD и SECRET_KEY
docker compose up --build
```

Открыть http://localhost:8000.

## Миграции

`entrypoint.sh` при старте выполняет `alembic upgrade head`, затем запускает
uvicorn. Начальные данные (роли, валюты, НДС, единицы, администратор)
создаются идемпотентно в lifespan приложения
(`app/services/seed_service.py::seed_all`).

Создание новой миграции:

```bash
export DATABASE_URL=postgresql+asyncpg://uwu:uwu@localhost:5432/uwu
alembic revision --autogenerate -m "описание"
alembic upgrade head
```

## Проверка готовности

Эндпоинт `/healthz` возвращает `{"status":"ok"}` (используется HEALTHCHECK в
`Dockerfile`). Перед деплоем обязательно прогнать тесты (см.
[testing](testing.md)).
