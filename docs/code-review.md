# Code Review UWU — находки для правок (этап 1)

> Свежий аудит кодовой базы, дополняющий [`AUDIT.md`](AUDIT.md). Тот документ описывал
> проблемы ядра (документы/остатки/права/безопасность) — бóльшая их часть уже исправлена.
> Здесь собраны **новые** находки, прежде всего по подсистемам, добавленным после первого
> аудита: AI-агент, боты/messaging, клиентский сайт/MiniApp, семантический поиск, а также
> остаточные проблемы ядра (логирование, god-файлы, деплой).
>
> Префиксы ID: **CORE** — ядро/логирование/деплой, **AG** — AI-агент, **BOT** — боты/messaging,
> **CUS** — клиентский сайт/MiniApp/site-менеджмент.
> Серьёзность: **Critical** > **High** > **Medium** > **Low**.

---

## 1. Сводка

Код в целом рабочий, первый аудит качественно закрыт (проверено: C1–C4, H1–H12, M5/M6/M16/M18,
M21 — исправлены). Главные системные проблемы, требующие правок:

1. **Логирование почти отсутствует в бизнес-слое.** Ядро (документы, остатки, кассы, справочники,
   отчёты) и весь web/api-слой пишут в лог только через HTTP-middleware в `main.py`. События
   «проведён документ», «списана партия», «изменён справочник», «сбой проведения» не логируются.
2. **Три god-файла** (`web/trade.py` ≈1938 строк, `services/report_service.py` ≈1151, `services/customer_service.py` ≈530) и
   дублирование логики web↔api и между адаптерами ботов.
3. **AI-агент — только «плоскость управления»**, сам агент и описанная в `docs/ai-agent.md` архитектура
   (LangGraph/HITL/approvals/memories) не реализованы → сильный дрейф документации и мёртвые поля.
4. **Ряд логических несостыковок** в новых подсистемах: скидки не доходят до чекаута, спуфинг/IDOR
   в agent-API, гонки без unique-констрейнтов, ложное «отправлено» в чатах.
5. **Деплой «из коробки» падает**: `docker-compose` по умолчанию выставляет `ENVIRONMENT=production`
   со слабыми секретами → `validate_security_settings()` отказывает в старте.

---

## 2. Логирование (главный пробел)

### CORE-L1. Бизнес-слой и web/api-слой не логируют ничего (High)
Единственные модули с логгером: `main.py`, `core/security.py`, `bots/*`, `services/agent_notify.py`,
`services/customer_service.py`, `services/miniapp_service.py`, `services/search_service.py`.

Без логгера: `services/document_service.py` (проведение/отмена — центральная операция),
`services/stock_service.py` (списание партий), `services/report_service.py`, `services/catalog_service.py`,
`services/cash_service.py`, `services/price_service.py`, `services/agent_service.py` (513 строк),
`services/chat_service.py`, `services/user_service.py`, `services/auth_service.py`, весь `web/`
(`trade.py` ≈1938 строк, `admin.py`, `agent_admin.py`, `site_admin.py`), весь `api/`.

Итог: в проде невозможно отследить, какой пользователь провёл/отменил документ, почему упало
списание, что менялось в справочниках (кроме БД-журнала `AuditLog`, который покрывает только документы).

**Фикс:** завести логгеры в сервисах (`document_service`, `stock_service`, `catalog_service`,
`cash_service`) и логировать ключевые мутации (`post/unpost`, `consume_batches` при `allow_negative`,
`set_rate`, открытие/закрытие смены) с `user_id` и `document_id`, без PII.

### CORE-L2. Двойное логирование необработанных исключений (Low)
`app/main.py:118-122` (middleware `log_requests`) логирует `Unhandled exception`, затем то же
исключение логируется ещё раз в `unhandled_exception_handler` (`main.py:147-152`) как `Unhandled error`.
Каждый 500 пишется в лог дважды.

**Фикс:** убрать `logger.exception` из middleware (оставить только в exception handler), либо
наоборот — оставить одну точку.

### CORE-L3. AuditLog пишет `created_by_id`, а не действующего пользователя для справочников (Medium)
`document_service._log` теперь принимает `user_id` (исправлено), но мутации справочников
(создание/изменение номенклатуры, контрагентов, кассовых смен) в `web/trade.py` вообще не пишут
`AuditLog` и не логируются. История изменений справочников отсутствует.

**Фикс:** добавить `AuditLog` (или хотя бы логгер) для catalog CRUD и кассовых смен.

---

## 3. Архитектура и структура

### CORE-A1. `web/trade.py` — god-module (High)
≈1938 строк, ~90 маршрутов: справочники + документы + РМК + инвентаризация + заявки + отчёты.
Нарушает SRP, тяжело поддерживать и тестировать. В `AUDIT.md` это L6 («разбить trade.py») — не сделано.

**Фикс:** разбить на `web/catalog_routes.py`, `web/document_routes.py`, `web/rmk_routes.py`,
`web/report_routes.py` с общим `router` в `web/router.py`; вынести парсинг форм в сервисы/схемы.

### CORE-A2. `services/report_service.py` — 1151 строк, 24 функции (Medium)
Все отчёты в одном файле; нет пагинации/`limit` (M2 из AUDIT остался отложенным); местами N+1 и
суммирование разных валют/фирм без фильтра.

**Фикс:** разделить на модули по тематике (`reports/stock.py`, `reports/sales.py`, `reports/money.py`,
`reports/settlements.py`); добавить пагинацию и cap периода; группировать по фирме/валюте.

### CORE-A3. Мёртвый код (Low, но накапливается)
- `app/models/enums.py:55,78,85` — `DocumentDirection`, `PaymentKind`, `ZakazState` — объявлены и
  импортированы в `models/__init__.py`, но **нигде не используются**.
- `app/core/config.py:45` — `debug: bool` не используется.
- `site_service.promotion_for` (`site_service.py:163`), `customer_service.clear_cart` (`:285`) — без вызовов.

**Фикс:** удалить или задействовать.

### CORE-A4. Дублирование логики между адаптерами ботов и web↔api (Medium)
`bots/telegram.py` и `bots/max.py` почти идентичный retry-цикл + `_RETRY_DELAY`; boilerplate
`create_adapter(...)/bot_manager.start(...)` продублирован в `service.py` (`apply_bot_config` и `start_bots`).
В customer логика создания заказа продублирована между `web.py` и `api.py`.

**Фикс:** базовый `PollingAdapter` с retry-циклом; единый helper `_start_adapter(...)`; общая логика
в сервис, тонкие роуты — только вызовы.

### CORE-A5. `_deny()` дублирует `require_permission` и отдаёт 303 вместо 403 (Low)
`web/trade.py:206-210` — 42 вызова; при нехватке прав — `RedirectResponse("/", 303)` вместо HTTP 403.
Несогласованно с `require_permission` (403). Аналогично в `web/agent_admin.py` и `web/site_admin.py`.

**Фикс:** унифицировать guard на `require_permission`, отдавать 403.

---

## 4. Логические несостыковки и баги

### CORE-B1. `docker-compose` «из коробки» не стартует (High)
`docker-compose.yml:40` `ENVIRONMENT: ${ENVIRONMENT:-production}`, а секреты по умолчанию —
`SECRET_KEY=change-me-to-a-long-random-string` (`:24`, входит в `_INSECURE_SECRETS`) и
`ADMIN_PASSWORD=admin` (`:26`, входит в `_WEAK_ADMIN_PASSWORDS`). `validate_security_settings()`
(`core/security.py:59-63`) в production возбуждает `RuntimeError` → контейнер уходит в restart-loop
на чистом `docker compose up`.

**Фикс:** либо `ENVIRONMENT` по умолчанию `development`, либо генерировать случайный `SECRET_KEY`
при первом запуске, либо явно требовать переменные без дефолтов и задокументировать это в README.

### CORE-B2. `_shift_window` всё ещё фильтрует по дате, а не по времени (Medium)
`services/cash_service.py:60-64` использует `shift.opened_at.date()` / `shift.closed_at.date()`.
Движение в тот же день, но вне окна смены (например, в 08:00 при открытии в 10:00), попадёт в
X/Z-отчёт. Docstring утверждает, что исправлено (добавлен фильтр по кассе и верхняя граница), но
гранулярность осталась дневная (M21 закрыт частично).

**Фикс:** сравнивать по полному `datetime` (`opened_at`/`closed_at`), а не `.date()`.

### CORE-B3. `catalog_service.update_one` не может сбросить поле в NULL (Low)
`services/catalog_service.py:49-51` — `if value is not None: setattr(...)`. Передать `None` означает
«не менять», а не «очистить». Нельзя убрать `kontragent_id`, `comment` и т.п. через этот путь.

**Фикс:** различать «не передано» и «явно null» (sentinel).

### CORE-B4. i18n: справочные подписи захардкожены по-русски (Medium)
`web/trade.py:71-97` — `DOC_LABELS` и `ZAKAZ_STATES` — русские строки, передаются в шаблоны
напрямую (мимо `translate()`). При выборе английского языка названия документов/состояний заявок
остаются русскими. Расходится с требованием ТЗ (RU/EN).

**Фикс:** вынести в `translations/*.json` и рендерить через `translate()`.

### CORE-B5. Миграции: revision-id созданы вручную, последовательные (Low)
`alembic/versions/*` — id вида `0a1b2c3d4e5f`, `0d1e2f3a4b5c`, `1e2f3a4b5c6d`… — рукописные
последовательности, а не случайные id Alembic. Цепочка валидна (один head `a9b0c1d2e3f4`), но такие
id хрупки (легко сгенерировать коллизию при параллельной работе) и сбивают с толку.

**Фикс:** при будущих миграциях использовать `alembic revision --autogenerate`; старые не трогать.

### CORE-B6. `requirements.txt` тащит тест-зависимости в прод-образ (Low)
`requirements.txt:23-25` содержит `pytest`/`pytest-asyncio`; Dockerfile (`:20`) ставит весь файл →
в production-образ попадают тестовые пакеты. `httpx` дублируется (в рантайме и dev в `pyproject`).

**Фикс:** разнести `requirements.txt`/`requirements-dev.txt` (или ставить только runtime).

### CORE-B7. Тесты строят схему через `create_all`, а не Alembic (Medium)
`tests/conftest.py:56-57` — `Base.metadata.create_all/drop_all`. Дрейф модель↔миграция не ловится
(если миграция не покрывает новую колонку модели — тесты зелёные, прод падает). `autoflush=False`
уже приведён к проду (исправлено), но не прогон миграций.

**Фикс:** CI-шаг `alembic upgrade head` на чистой БД; тестовая БД — из миграций.

---

## 5. AI-агент (подсистема добавлена после первого аудита)

### AG-1. `rate_limit` инструментов хранится, но не применяется (High)
`models/agent.py:106`, `api/agent.py:86`, `services/agent_service.py:462` — поле заводится и отдаётся,
но нигде не enforcement. `docs/ai-agent.md` §11 обещает rate limiting против DoS/зацикливания — не реализовано.

**Фикс:** применить `SlidingWindowRateLimiter` по ключу `(api_key.id, tool_key)` в эндпоинтах инструментов,
либо убрать поле и обещание из доки.

### AG-2. API-ключи всегда получают полный набор прав (High)
`services/agent_service.py:382` — default `list(AGENT_PERMISSIONS)` (включая `documents.write`);
`web/agent_admin.py:277` создаёт ключ без выбора прав. Принцип наименьших привилегий нарушен —
read-only ключ создать нельзя.

**Фикс:** чекбоксы прав в форме создания ключа, дефолт — read-only.

### AG-3. Коллизия версий промпта после rollback (High)
`services/agent_service.py:275` — `next_version = prompt.active_version + 1`. После отката на v1 следующий
`add_prompt_version` снова создаст v2 (дубликат). Нет `UniqueConstraint(prompt_id, version)`;
`active_template` (`:226-234`) → `MultipleResultsFound`.

**Фикс:** `next_version = max(version)+1` по prompt_id; `UniqueConstraint("prompt_id","version")` + миграция.

### AG-4. Polling `/api/agent/inbox` зацикливается (High)
`api/agent.py:96-119` — только `SELECT is_read=False`, нет update/ack. Агент в polling-режиме бесконечно
обрабатывает одни и те же входящие (дубли ответов). Webhook-путь (`agent_notify`) проблемы не имеет.

**Фикс:** `POST /api/agent/inbox/ack` (атомарный `UPDATE ... SET is_read=true WHERE id IN (...) RETURNING`).

### AG-5. `POST /api/agent/messages` без идемпотентности и валидации (High)
`api/agent.py:122-163` — `author` полностью клиентский (спуфинг "operator"/"customer"), `agent_run_id`
не проверяется (невалидный → IntegrityError/500), нет ключа идемпотентности (retry → дубль), commit до доставки.

**Фикс:** валидировать `author` по белому списку, проверять `agent_run_id`, добавить idempotency-ключ,
возвращать 4xx вместо 500.

### AG-6. Дрейф документации: «отдельный сервис + HITL» vs фактическая реализация (High)
`docs/ai-agent.md` описывает отдельный контейнер `uwu-ai-agent`, LangGraph, HITL
(`agent_approvals`, `agent_memories`, `approval_policy`, эндпоинты `/api/agent/approvals`) — ничего из
этого в моделях нет (`models/agent.py` явно: «одобрение полностью убрано»). В репозитории только
«плоскость управления» + REST-контракт. `DEFAULT_AGENT_CONFIG["fallback_message"]` нигде не используется.

**Фикс:** привести `docs/ai-agent.md` к фактическому статусу (пометить HITL/approvals/memories как
roadmap/удалённое), задействовать или убрать `fallback_message`.

### AG-7. `customer_insights` игнорирует `lookback_days` (Medium)
`services/agent_service.py:497-520` — `start` вычисляется, но `sale_agg` и история НЕ фильтруются по дате
(только `top_items`). `orders_count`/`total_spent` считаются за всё время, а не за 90 дней.

**Фикс:** добавить `Document.date >= start` в оба запроса.

### AG-8. Wildcard-инъекция в `keyword_search` (Medium)
`services/search_service.py:57-62` — `name.ilike(f"%{query}%")` без экранирования `%`/`_`/`\`;
пробельный query → `%%` вернёт всю номенклатуру.

**Фикс:** экранировать wildcard (ESCAPE), `.strip()` и отклонять пустой/короткий query.

### AG-9. IDOR: любой валидный ключ читает любые данные (Medium)
`api/agent.py:288-304` (`get_zakaz`), `:166-209` (`context/{chat_id}`), `:425-440` (`customer/{id}`) —
без scoping на принадлежность. В сочетании с AG-2 (полные права) — перечисление заказов/чатов/профилей по id.

**Фикс:** read-only ключ по умолчанию + журналирование; при необходимости scoping ключ→chat/customer.

### AG-10. `create_order`: нет верхней границы количества и берётся произвольный first-match (Medium)
`api/agent.py:396-407` — проверяется только `quantity <= 0`; `keyword_search(limit=1)` берёт первое
совпадение по неоднозначному имени.

**Фикс:** ограничить quantity сверху; при нескольких кандидатах возвращать `created=false` с просьбой уточнить.

### AG-11. Embedding-провайдер: не-JSON ответ → 500 вместо fallback (Medium)
`services/embedding_service.py:64-74` — `resp.raise_for_status()` ловится, но `resp.json()` (`:68`) вне try —
`JSONDecodeError` не оборачивается в `EmbeddingError` → `search_semantic` вернёт 500.

**Фикс:** обернуть парсинг JSON в try → `EmbeddingError`.

### AG-12. `EMBEDDING_DIM` захардкожен; `settings.embedding_dim` мёртв (Medium)
`models/embeddings.py:23` (`EMBEDDING_DIM=1536`) против `config.py:64` (`embedding_dim`) — настройка не читается;
`search_service.py:100` сверяет по константе модели. Комментарий «должна совпадать» — ложная гарантия.

**Фикс:** убрать `settings.embedding_dim` или проверять по нему + сверка с константой при старте.

### AG-13. `rebuild_embeddings`: нет rollback и очистки осиротевших (Medium)
`services/search_service.py:128-170` — коммит побатчево без try/rollback; при удалении номенклатуры
`NomenklaturaEmbedding` остаётся (FK без ondelete) → расхождение `embeddings_status` count и реально ищущихся.

**Фикс:** rollback на ошибку, cleanup orphan при пересборке, `ondelete="CASCADE"`.

### AG-14. `verify_key` пишет `last_used_at` + commit на каждый запрос (Medium)
`services/agent_service.py:414-416` — write-амплификация и contention на каждый вызов агента.

**Фикс:** обновлять `last_used_at` лениво/по таймеру, не коммитить на чтение.

### AG-15. `set_configs` коммитит по одному ключу (Medium)
`services/agent_service.py:204-207` — частичный сбой оставляет половину настроек сохранёнными.

**Фикс:** один commit в конце (bulk upsert).

### AG-16. Мелкие (Low)
- `notify_agent` fire-and-forget без трекинга задачи → «Task was destroyed» (объединить с BOT-4).
- `notify_agent` вызывается с разной сигнатурой в ботах (без `customer_id`) и в site (с ним) → персонализация недоступна на bot-каналах.
- `RUN_STATUSES` (`models/agent.py:27`) — мёртвая константа; `AgentRun.status` не валидируется.
- `expires_at` — мёртвая фича (админка не задаёт срок; сравнение с naive datetime → TypeError).
- `agent_save_config` сохраняет ВСЕ поля формы как config-ключи без whitelist.
- `_require_admin` инвертирован (`return not user.is_admin`) и отдаёт 303 вместо 403; тонкие права `agent.*.manage` (объявлены в `users.py`) игнорируются.
- `embedding_service.get_client` кэширует синглтон (комментарий утверждает обратное), `aclose` не вызывается.
- `RunCreate` — mutable default-аргументы (`prompt_versions={}`, `tool_calls=[]`).

---

## 6. Боты и messaging

### BOT-1. Сообщение коммитится ДО доставки; сбой доставки молча глотается (High)
`api/messaging.py:157-167` и `api/agent.py:140-155` — Message + commit, затем `deliver_outgoing`
(`bots/service.py:233-240`) ловит `Exception` и ничего не возвращает; эндпоинт всегда 201. Оператор видит
«отправлено», а клиент не получил (сбой сети / невалидный chat_id / лимит Telegram 4096).

**Фикс:** валидировать длину до persist; `deliver_outgoing` возвращать статус; ввести `delivery_status`/`delivery_error`
или писать out-сообщение только после успешной доставки.

### BOT-2. Нет лимита длины исходящих сообщений оператора/агента (High)
`api/messaging.py:25-26` и `api/agent.py:122-126` — `text` без `max_length`, тогда как путь покупателя
(`customer/api.py:216-217`) имеет лимит 4000. Несогласованность + переполнение БД + сбой Telegram 4096.

**Фикс:** `text: str = Field(..., max_length=4000)` в обеих схемах.

### BOT-3. `bot_manager.start()` при hot-reload отменяет задачу без await/shutdown (Medium)
`bots/service.py:55-58` — `old_task.cancel()` не ожидается, `adapter.shutdown()` не вызывается →
незавершённая задача (RuntimeWarning) и утечка aiohttp-сессии. Остаток M15.

**Фикс:** перед пересозданием `await self.stop(channel)` либо сохранить задачу и `await gather`.

### BOT-4. `notify_agent` fire-and-forget без трекинга (Medium)
`services/agent_notify.py:55` — `asyncio.create_task(...)` без сохранения ссылки → «Task was destroyed
but it is pending» при shutdown; `RuntimeError` без running loop. (Совпадает с AG-16.)

**Фикс:** трекать задачи (set + `add_done_callback`) и `await` при shutdown.

### BOT-5. `find_or_create_chat` — гонка TOCTOU, нет unique на (channel, external_id) (Medium)
`bots/service.py:182-194`; `models/messaging.py:28` — `external_id` только `index=True`. Два конкурентных
первых сообщения одного external_id создадут два `Chat` → раскол переписки.

**Фикс:** `UniqueConstraint("channel","external_id")` + обработка `IntegrityError`.

### BOT-6. `toggle_agent` требует только `documents.read`, но меняет состояние (Medium)
`api/messaging.py:71-83` против `send_message` (`:151`, требует `documents.write`). Пользователь с правом
только на чтение может вкл/выкл автоответ агента.

**Фикс:** требовать `documents.write` (или отдельное право).

### BOT-7. MAX-адаптер: `msg.recipient` может быть None → AttributeError (Medium)
`bots/max.py:44` — `msg.recipient.chat_id` без проверки → падение обработчика, сообщение теряется.

**Фикс:** `external_id = str(msg.recipient.chat_id or "") if msg.recipient is not None else ""`.

### BOT-8. Очистка сессии при отмене пропускается (Medium)
`bots/telegram.py:69-70` — `await self._bot.session.close()` не в `finally`; `CancelledError` (BaseException)
обходит закрытие → утечка aiohttp-сессии.

**Фикс:** `try/finally` с закрытием сессии.

### BOT-9. Мелкие (Low)
- PII в логах: `bots/service.py:215-220` логирует `sender_name` (ФИО из мессенджера) и `external_chat_id`.
- `BotManager.stop()` молча глотает исключения задачи (`except (...): pass`).
- `unread_count` отдаёт полный `last.text` без обрезки (poll каждые 3с → раздутый ответ).
- Нет способа очистить токен бота через UI (пустой токен сохраняет старый).
- `apply_bot_config` перезапускает адаптер даже без изменений.
- `Chat.name` site-чата хранит телефон покупателя (сырой PII всем операторам).
- Общий inbox `/api/chats/*` без scoping по фирме (связано с multi-tenancy M4).
- Устаревший docstring `api/messaging.py:3-4` («доставка не реализована») — неверно.

---

## 7. Клиентский сайт / MiniApp / site-менеджмент

### CUS-1. Скидки не применяются к корзине/чекауту — переплата (Critical)
`customer_service.py:225` (`get_cart_items`: `price = n.retail_price`) и `:341` (`checkout` берёт `i["price"]`),
а `available_products` (`:173-182`) применяет `site_service.apply_discount`. Покупатель видит цену со скидкой
в каталоге, но платит полную.

**Фикс:** единообразно применять скидку (или сохранять цену со скидкой) в `get_cart_items`/`checkout`.

### CUS-2. MiniApp account-takeover через synthetic-phone preimage (Critical)
`miniapp_service.py:146-153` — `synthetic_phone = f"ma_{channel}_{external_id}"` живёт в том же уникальном
пространстве `Customer.phone`. Атакующий регистрирует обычный аккаунт с телефоном `ma_telegram_<victim_id>`;
потом жертва логинится в MiniApp → `get_customer_by_phone(synthetic_phone)` находит аккаунт атакующего,
привязывает к нему Telegram-id жертвы.

**Фикс:** отдельная не-phone колонка идентичности (`external_key`) или привязка только через `CustomerBinding`
без lookup по phone-preimage.

### CUS-3. `find_or_create_customer` гонка → 500 (High)
`miniapp_service.py:140-154` — check-then-insert для `Customer` (unique phone) и `CustomerBinding`
(unique channel+external_id) без `except IntegrityError`. Два конкурентных первого логина → 500.

**Фикс:** `except IntegrityError` + re-fetch, либо `INSERT ... ON CONFLICT`.

### CUS-4. initData: окно свежести 24ч + PII в URL/логах (High)
`miniapp_service.py:35` — `MAX_INIT_DATA_AGE_SECONDS = 24*3600` (в AUDIT рекомендовано 1–5 мин);
`miniapp.py:117` — Telegram-bridge пишет полный `initData` (PII: имя/username/photo + hash) в `window.location`
→ попадает в access-логи, историю браузера, referrer. Утёкший URL replayable 24ч.

**Фикс:** окно ≤5 мин; передавать initData POST'ом вместо GET-query; не логировать query-строки.

### CUS-5. `add_to_cart` игнорирует `is_published`/`is_active` (High)
`customer_service.py:253` — только `session.get(Nomenklatura, id) is not None`. Можно добавить и заказать
неопубликованный/архивный товар по угаданному id (IDOR скрытого каталога).

**Фикс:** проверять `is_published` и не-архивность в `add_to_cart` и повторно в `checkout`.

### CUS-6. Чекаут: TOCTOU + игнор резервов + сумма по всем складам (Medium)
`customer_service.py:316-322` — `get_balance` без `with_for_update`, сумма по всем складам, без вычета
`Reservation` (`get_available`). Проверка advisory-only, вводит в заблуждение.

**Фикс:** блокировать или убрать проверку; если оставлять — `get_available`.

### CUS-7. Чекаут: гонка двойного сабмита (Medium)
`customer_service.py:311-370` — чтение items → удаление строк корзины → `create_document` без
`with_for_update` и без idempotency-key → два конкурентных checkout дают дубль ZAKAZ.

**Фикс:** `with_for_update` на строках корзины или ключ идемпотентности.

### CUS-8. Несогласованное сопоставление телефона между checkout и agent-путём (Medium)
`match_kontragent_by_phone` (`:305`) — точное `==` по нормализованному (с `+`); а
`match_customer_by_phone`/`resolve_customer_by_phone` (`:393-410`, `:453-470`) пробуют варианты
`{normalized, digits, "+"+digits}`. Один и тот же контрагент может не совпасть в checkout, но совпасть в агенте.

**Фикс:** единая нормализация + варианты сопоставления.

### CUS-9. `set_cart_quantity` обходит `MAX_CART_QUANTITY` (Medium)
`customer_service.py:281` — нет верхней границы; огромное значение → переполнение `Numeric(14,3)` → 500.

**Фикс:** применить тот же cap и валидацию.

### CUS-10. `CartItem` без unique на (cart_id, nomenklatura_id) (Medium)
`models/customer.py:59-66`; `add_to_cart` (`:256-265`) check-then-insert → дубли строк при конкурентном add.

**Фикс:** `UniqueConstraint("cart_id","nomenklatura_id")`.

### CUS-11. `delete_customer` ломается на miniapp-привязанных (Medium)
`customer_service.py:118-120` — hard-delete; `CustomerBinding.customer_id` без cascade → `IntegrityError` 500;
заказы с `extra.customer_id` осиротевают.

**Фикс:** удалять bindings первым (или cascade), определить судьбу заказов.

### CUS-12. `site_admin`: невалидированный `int()` → 500 (Medium)
`site_admin.py:177-178` — `int(nomenklatura_id)`/`int(category_id)` на сыром вводе; нечисловой → `ValueError`.

**Фикс:** парсить защищённо (как `_as_decimal`).

### CUS-13. Значения промо не валидируются (Medium)
`site_service.py:56-83` + `site_admin.py:169-181` — отрицательный процент (повышение цены), процент >100,
`discount_type` с fallback на percent для любого неизвестного, `fixed` > price, `_as_decimal` принимает
`Decimal("NaN")`/`"Infinity"` → переполнение Numeric/500.

**Фикс:** валидация 0≤percent≤100, fixed≥0, whitelist type, reject NaN/Inf.

### CUS-14. Site-менеджмент на `is_admin`, а не на правах (Medium)
`site_admin.py:46-48,77` — `_require_admin` (async без await, инвертированный return) редиректит 303 вместо 403;
права `site.manage` нет. Несогласованно с `require_permission`.

**Фикс:** permission-guard + 403.

### CUS-15. Нет rate limiting на customer auth/chat (Medium)
`customer/api.py:73` (login), `:62` (register), `:207` (chat) — без ограничений (H3 закрыт только для
сотрудников). Брутфорс/спам не ограничены.

**Фикс:** `slowapi`/`fastapi-limiter` по IP+телефон.

### CUS-16. Пароль: нет верхней границы → bcrypt-обрезка 72 байта (Medium)
`customer_service.py:81-82` (только min 6); bcrypt обрезает на 72 байта → два разных длинных пароля дают
один хеш.

**Фикс:** reject >72 байт (или pre-hash), добавить разумный max.

### CUS-17. Мелкие (Low)
- `get_cart` (`:203-211`) создаёт корзину через `flush()` на GET `/cart` (side-effect на чтении).
- `web.py:171-190` `cart_add`/`cart_update` молча `except CustomerError: pass` — нет обратной связи.
- `web.py:142-146` logout через GET; cookie без `max_age`/`expires`; нет CSRF на customer POST.
- `order_context` N+1 (`customer_service.py:614-615` — `session.get` на каждую позицию).
- `list_customer_orders` (`:599-608`) тянет ВСЕ ZAKAZ и фильтрует в Python — нет фильтра по customer_id, нет пагинации.
- `available_products` `ilike(f"%{search}%")` без экранирования и без cap длины.
- `site_service.set_settings` (`:31-41`) хранит произвольные ключи/значения; `banner_link` может быть
  `javascript:` URL (XSS, если рендерится как href).
- Decimal суммы сериализуются как float в API-ответах (`customer/api.py:160,170,184`) → потеря точности.
- `authenticate` (`:105-107`) пропускает bcrypt при несуществующем телефоне → timing side-channel; `register`
  раскрывает факт существования телефона.

---

## 8. Пробелы тестового покрытия

Существующие тесты (27 файлов) покрывают happy-path ядра и новые подсистемы, но отсутствуют:

- **Ядро:** `cash_service` (open/close/X-Z), `stock_service` напрямую, race conditions (C2/C3), откат
  проведения с FIFO/LIFO-восстановлением по значениям, CSRF/rate-limit, 403-кейсы веб-слоя.
- **Agent:** rate limit (AG-1), ограниченные права ключа (AG-2), коллизия версий промпта (AG-3),
  ack/inbox (AG-4), идемпотентность/спуфинг author (AG-5), wildcard-инъекция (AG-8), IDOR (AG-9),
  не-JSON ответ провайдера (AG-11).
- **Bots:** `BotManager.start()` перезапуск (BOT-3), `stop_all()`, `apply_bot_config` START-ветка,
  закрытие сессии при cancel (BOT-8), `MaxAdapter` полностью, `deliver_outgoing` ветка исключения (BOT-1),
  `notify_agent` (BOT-4), 403-кейсы (BOT-6).
- **Customer/site:** скидка в чекауте (CUS-1), takeover через synthetic-phone (CUS-2), конкурентный
  `find_or_create_customer` (CUS-3), границы окна свежести initData (CUS-4), заказ неопубликованного (CUS-5),
  двойной сабмит чекаута, верхняя граница `set_cart_quantity`, `delete_customer` с bindings, нечисловые
  промо-id, границы валидации промо (negative percent, NaN). `test_miniapp.py` покрывает только dev-mode,
  не продакшен-путь `/shop/mini` с подписью. `site_service` и `site_admin` не тестируются вовсе.

---

## 9. Приоритеты и рекомендуемый порядок

| Приоритет | ID | Тема |
|---|---|---|
| **Critical** | CUS-1 | Скидки не доходят до чекаута (переплата клиентов) |
| | CUS-2 | MiniApp account-takeover через synthetic-phone |
| **High** | CORE-B1 | docker-compose не стартует из коробки |
| | CORE-L1 | Логирование бизнес-слоя отсутствует |
| | CORE-A1 | god-module `web/trade.py` |
| | AG-1..AG-6 | agent: rate-limit, права ключей, версии промптов, inbox-ack, валидация, дрейф доки |
| | BOT-1, BOT-2 | ложное «отправлено», нет лимита длины сообщений |
| | CUS-3..CUS-5 | гонки miniapp, окно initData 24ч, IDOR неопубликованных товаров |
| **Medium** | CORE-B2..B7, CORE-A2..A5 | смены по дате, i18n, миграции, тесты-через-create_all |
| | AG-7..AG-16, BOT-3..BOT-8, CUS-6..CUS-16 | остальное |
| **Low** | AG-16, BOT-9, CUS-17, CORE-L2/L3, CORE-A3 | мёртвый код, PII в логах, стиль |

**Рекомендуемый порядок устранения (этап 2):**
1. **CUS-1, CUS-2, CORE-B1** — деньги клиентов, захват аккаунта и невозможность деплоя.
2. **CORE-L1** — сквозное логирование бизнес-действий (основа для диагностики всех дальнейших правок).
3. **BOT-1, BOT-2, CUS-4, CUS-5** — корректность доставки/безопасность мессенджеров и магазина.
4. **AG-1..AG-6** — безопасность и целостность agent-подсистемы + актуализация `docs/ai-agent.md`.
5. **CORE-A1/A2** — декомпозиция god-файлов (делать вместе с правками, не отдельно).
6. Остальное по мере разработки.

---

## 10. Открытые вопросы к автору

1. **«Два репозитория»**: в `C:\UWU` обнаружен один git-репозиторий (ветка `main`, чистый). Конфиг и
   `docs/ai-agent.md` ссылаются на отдельный сервис `uwu-ai-agent`, которого нет ни в этом репозитории,
   ни в `docker-compose.yml`. Уточните: (а) где второй репозиторий и надо ли его тоже аудировать,
   (б) является ли AI-агент отдельным сервисом (тогда нужно добавить его в compose и синхронизировать контракт)
   или он должен быть реализован внутри этого репозитория (тогда `docs/ai-agent.md` надо переписать)?
2. **Multi-tenancy (M4 из AUDIT)**: фирмы/валюты в движениях частично добавлены (`firma_id`), но scoping
   по фирме в отчётах/чатах/каталоге не реализован. Это осознанное «одна база — одна фирма» на данном этапе,
   или нужно закладывать разграничение сейчас?
