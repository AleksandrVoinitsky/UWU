# uwu-ai-agent

AI-консультант покупателей UWU — **отдельный контейнер** (и потенциально
отдельный репозиторий), являющийся *клиентом* REST API ядра UWU. Агент не пишет
в базу данных напрямую и не дублирует бизнес-логику: все данные и действия идут
через эндпоинты `/api/agent/*` ядра (API-key аутентификация).

Полная спецификация — в ядре: [`docs/ai-agent.md`](../docs/ai-agent.md) и
[`ROADMAP.md`](../ROADMAP.md).

## Что делает

1. Принимает входящие сообщения покупателей (polling `/api/agent/inbox` и/или
   webhook `POST /webhook`).
2. Оркестрирует ответ: **классификация намерения → сбор контекста → генерация**
   (узлы повторяют дизайн графа LangGraph из `docs/ai-agent.md`).
3. Вызывает инструменты-обёртки над API ядра: `search_catalog`, `get_stock`,
   `get_zakaz`, `add_to_cart`, `create_order`, `match_customer`,
   `customer_insights`.
4. Публикует ответ обратно в чат через `POST /api/agent/messages` и пишет
   результат запуска в журнал `agent_runs` (аудит).

## Режимы работы

| Режим | Условие | Поведение |
| --- | --- | --- |
| LLM | задан `LLM_API_KEY` | ответы через OpenAI-совместимый API (классификация + генерация) |
| Fallback | `LLM_API_KEY` пуст | детерминированный ответчик по ключевым словам (работает «из коробки») |

Промпты и права агента управляются в админке ядра (`/admin/agent/*`), а не в
коде агента. Модель/параметры LLM задаются переменными окружения **этого**
сервиса.

## Быстрый старт (Docker Compose)

```bash
# в корне репозитория UWU
cp .env.example .env          # задать AGENT_API_KEY (общий с ядром)
docker compose up --build
```

Ядро доступно на http://localhost:8000, агент — на http://localhost:8100/healthz.

## Конфигурация

Все переменные — в [`.env.example`](.env.example). Ключевые:

- `CORE_BASE_URL` — URL ядра (`http://app:8000` внутри compose-сети).
- `AGENT_API_KEY` — API-ключ (тот же, что передан ядру через `AGENT_API_KEY`;
  ядро при старте гарантирует существование ключа с таким значением).
- `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` — OpenAI-совместимый провайдер.
- `POLL_INTERVAL` / `ENABLE_POLLING` — частота и признак polling-цикла.

## Структура

| Модуль | Назначение |
| --- | --- |
| [`app/main.py`](app/main.py) | control-plane FastAPI: `/healthz`, `/webhook`, polling-цикл |
| [`app/config.py`](app/config.py) | настройки (pydantic-settings) |
| [`app/core_client.py`](app/core_client.py) | тонкий HTTP-клиент `/api/agent/*` |
| [`app/graph.py`](app/graph.py) | оркестрация (намерение → контекст → генерация) |
| [`app/llm.py`](app/llm.py) | OpenAI-совместимый LLM (ленивый импорт) |
| [`app/responder.py`](app/responder.py) | детерминированный fallback-ответчик |

## Тесты

```bash
pip install -r requirements.txt
pytest
```

## Безопасность

- Аутентификация ядром по API-ключу (минимальные права `AGENT_PERMISSIONS`).
- Жёсткая защитная рамка в системном промпте (не зависит от промптов админки).
- Данные из сообщений трактуются как данные, а не инструкции.
- Каждый запуск фиксируется в `agent_runs` (трассировка/аудит).
