# Развёртывание (Docker)

## Состав

`docker-compose.yml` поднимает два сервиса:

1. **db** — PostgreSQL 16 с расширением **pgvector** (образ
   `pgvector/pgvector:pg16`; нужен для семантического поиска), том `pgdata`.
2. **app** — UWU (FastAPI + uvicorn), порт 8000.

> ⚠️ Для семантического поиска (`/api/agent/search_semantic`) используется
> расширение `vector`. При миграции с обычного образа `postgres` на
> `pgvector/pgvector:pg16` существующий том данных можно сохранить, но нужно
> вручную выполнить `CREATE EXTENSION IF NOT EXISTS vector` (миграция
> `b1c2d3e4f5a6_embeddings.py` делает это автоматически).

## Переменные окружения

Задаются в `.env` (см. `.env.example`):

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://uwu:uwu@db:5432/uwu?ssl=disable` | Строка подключения (SSL отключён — внутренняя сеть Docker) |
| `ADMIN_LOGIN` | `admin` | Логин администратора |
| `ADMIN_PASSWORD` | `admin` | Пароль администратора |
| `ADMIN_EMAIL` | `admin@uwu.local` | Email администратора |
| `SECRET_KEY` | `change-me-...` | Ключ подписи JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | Срок жизни токена |
| `ENVIRONMENT` | `development` | `development` \| `production`. В `production` небезопасные `SECRET_KEY`/`ADMIN_PASSWORD` блокируют запуск (fail-fast) |
| `DEFAULT_CURRENCY` | `RUB` | Валюта по умолчанию |
| `DEFAULT_LANGUAGE` | `ru` | Язык интерфейса по умолчанию |
| `EMBEDDING_BASE_URL` | *(пусто)* | OpenAI-совместимый эндпоинт эмбеддингов (семантический поиск) |
| `EMBEDDING_API_KEY` | *(пусто)* | Ключ провайдера эмбеддингов |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Модель эмбеддингов |

## Запуск

```bash
cp .env.example .env
# отредактировать ADMIN_PASSWORD и SECRET_KEY
docker compose up --build
```

Открыть http://localhost:8000.

> Для разработки `ENVIRONMENT=development` (по умолчанию) — слабые секреты
> допустимы (в лог пишется предупреждение). Для продакшена задайте
> `ENVIRONMENT=production` и надёжные `SECRET_KEY`/`ADMIN_PASSWORD` — иначе
> сервис откажется стартовать (fail-fast).

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
