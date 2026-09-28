# Контракт ядра UWU (REST API, потребляемый агентом)

> Фиксирует поверхность API ядра, на которую опирается `uwu-ai-agent`. Ядро —
> единственный источник бизнес-логики и данных; агент — клиент, а не часть учёта.
> При изменении эндпоинта контракт-тесты агента должны «покраснеть».

## Аутентификация

Все эндпоинты `/api/agent/*` требуют API-ключ агента (`Authorization: Bearer <key>`
или `X-Api-Key: <key>`). Ключ хешируется (SHA-256) в таблице `agent_api_keys` и
носит ограниченный набор прав `AGENT_PERMISSIONS` (`catalog.read`,
`documents.read`, `documents.write`, `reports.read`). Ключ задаётся переменной
`AGENT_API_KEY` в ядре (создаётся при старте) и в агенте.

## Эндпоинты

| Эндпоинт | Метод | Назначение | Право |
| --- | --- | --- | --- |
| `/api/agent/inbox` | GET | непрочитанные входящие сообщения | — |
| `/api/agent/inbox/read` | POST | пометить входящие прочитанными (`{message_ids: []}`) | — |
| `/api/agent/messages` | POST | опубликовать ответ агента (`{chat_id, text}`) | — |
| `/api/agent/context/{chat_id}` | GET | профиль/корзина/история чата | — |
| `/api/agent/prompts` | GET | активные промпты (кэш) | — |
| `/api/agent/tools` | GET | включённые инструменты (реестр) | — |
| `/api/agent/runs` | POST | записать запуск в журнал (аудит) | — |
| `/api/agent/search_catalog?query=` | GET | поиск товаров (название/артикул) | `catalog.read` |
| `/api/agent/get_stock?nomenklatura_id=` | GET | остаток товара | `catalog.read` |
| `/api/agent/get_cart?customer_id=` | GET | корзина покупателя | `catalog.read` |
| `/api/agent/get_zakaz?order_id=` | GET | статус/состав заявки | `documents.read` |
| `/api/agent/match_customer?phone=` | GET | найти покупателя по телефону | `documents.read` |
| `/api/agent/add_to_cart` | POST | добавить в корзину | `documents.write` |
| `/api/agent/create_order` | POST | создать заявку (DRAFT) | `documents.write` |
| `/api/agent/customer/{id}` | GET | персонализация (история/рекомендации/память) | `reports.read` |
| `/api/agent/search_semantic` | POST | семантический поиск (pgvector) | `catalog.read` |

## Форматы (ключевые)

- `inbox`: `[{message_id, chat_id, chat_name, channel, customer_id, text, created_at}]`.
- `messages` (ответ): `{chat_id, text, author="agent", agent_run_id?}`.
- `search_catalog` → `[{id, name, full_name, artikul, price, stock}]`.
- `create_order` → `{created: bool, order? | error?}`; при `created=false` агент
  читает `error` и уточняет у покупателя.

## Модель потока

входящее → агент (`inbox`/webhook) → граф (намерение → контекст → генерация) →
`POST /messages` → ядро доставляет ответ в мессенджер/чат. Агент после обработки
вызывает `/inbox/read`, чтобы не обрабатывать сообщение повторно.

## См. также

- [`../README.md`](../README.md) — обзор и структура агента.
- Ядро: `docs/ai-agent.md`, `app/api/agent.py`, `app/models/agent.py`.
