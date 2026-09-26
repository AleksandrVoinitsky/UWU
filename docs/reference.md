# Справочник функций

Техническое описание и назначение функций по модулям. Ссылки ведут на файлы
исходного кода.

## app/core/config.py

### `class Settings`
Настройки приложения (pydantic-settings). Читаются из переменных окружения
(`.env`). Поля: `database_url`, `admin_login`, `admin_password`, `secret_key`,
`default_currency`, `default_language` и др.

### `get_settings() -> Settings`
**Назначение:** возвращает кэшированный (`@lru_cache`) экземпляр настроек.
**Технически:** одиночка настроек на процесс; гарантирует, что все модули видят
одну конфигурацию.

## app/core/database.py

### `engine`
**Назначение:** глобальный async-движок SQLAlchemy (asyncpg).
**Технически:** `create_async_engine(..., pool_pre_ping=True)`.

### `class Base`
**Назначение:** базовый класс всех ORM-моделей (Declarative).

### `get_session() -> AsyncGenerator[AsyncSession, None]`
**Назначение:** FastAPI-зависимость, выдающая сессию и закрывающая её после запроса.
**Технически:** `async with async_session_factory() as session: yield session`.

## app/core/security.py

### `hash_password(password) -> str`
**Назначение:** bcrypt-хеш пароля. **Технически:** `bcrypt.hashpw` с авто-солью.

### `verify_password(password, hashed) -> bool`
**Назначение:** проверка пароля. **Технически:** `bcrypt.checkpw`, `ValueError` → `False`.

### `create_access_token(subject, expires_minutes=None) -> str`
**Назначение:** JWT для пользователя. **Технически:** HS256, `sub`, `exp`, `iat`.

### `decode_access_token(token) -> str | None`
**Назначение:** декодирование JWT → `sub`. **Технически:** `None` при `PyJWTError`.

## app/core/deps.py

### `get_current_user(token, session) -> User`
**Назначение:** текущий пользователь из Bearer-токена (REST).
**Технически:** декодирует токен, загружает `User`, проверяет `is_active`; иначе 401.

### `require_admin(user) -> User`
**Назначение:** пропускает только администраторов (403 иначе).

### `get_current_user_optional(request, session) -> User | None`
**Назначение:** пользователь из cookie (веб), `None` если не аутентифицирован.

### `get_current_user_from_cookie(request, session) -> User`
**Назначение:** требует аутентификации по cookie (веб), 401 иначе.

## app/core/i18n.py

### `translate(key, lang=None, **kwargs) -> str`
**Назначение:** перевод ключа (`app/translations/{lang}.json`); при отсутствии —
сам ключ. **Технически:** `@lru_cache` загрузка словаря, `str.format` для плейсхолдеров.

### `t` — короткий алиас `translate` (используется в шаблонах).

## app/models/enums.py

### `class StrEnum(str, enum.Enum)`
**Назначение:** строковое перечисление; `str(value)` возвращает значение.

Содержит перечисления: `NomenklaturaVid`, `KontragentVid`, `SkladTip`,
`DocumentStatus`, `DocumentDirection`, `CostMethod`, `RestockControl`,
`PaymentKind`, `ZakazState`, `RoleKey`, `DocType`, `DocSubtype`.

## app/services/auth_service.py

### `authenticate(session, login, password) -> str`
**Назначение:** проверка логина/пароля, возврат JWT.
**Технически:** `get_user_by_login` + `verify_password` + `is_active`; иначе `AuthError`.

### `get_user_by_login(session, login) -> User | None`
**Назначение:** поиск пользователя по логину.

## app/services/user_service.py

### `list_users`, `get_user`, `create_user`, `update_user`, `delete_user`
**Назначение:** CRUD пользователей (доступно администратору).

### `list_roles`, `get_role`, `create_role`, `update_role`
**Назначение:** CRUD ролей.

### `seed_default_roles(session)`
**Назначение:** создаёт встроенные роли (admin/operator/accountant), если их нет.

## app/services/catalog_service.py

### `list_all(session, model)`, `get_one`, `create_one`, `update_one`, `delete_one`
**Назначение:** универсальные CRUD-операции для справочников.

### `next_code(session, model, prefix="") -> str`
**Назначение:** следующий числовой код справочника (001, 002, …).

### `next_nomenklatura_code`, `next_kontragent_code`
**Назначение:** автогенерация кодов номенклатуры/контрагентов.

### `get_constants(session) -> dict`
**Назначение:** все константы (со значениями по умолчанию из `DEFAULT_CONSTANTS`).

### `set_constant(session, key, value)`
**Назначение:** установка константы (создание при отсутствии).

## app/services/stock_service.py

### `get_balance(session, nomenklatura_id, sklad_id=None) -> Decimal`
**Назначение:** остаток номенклатуры (по складу или суммарно).
**Технически:** `SUM(StockBatch.quantity)`.

### `get_balances(session, sklad_id=None) -> list`
**Назначение:** остатки по всем позициям (для отчёта).

### `create_incoming(session, *, document_id, date, nomenklatura_id, sklad_id, quantity, price) -> StockBatch`
**Назначение:** оприходование партии + движение прихода.

### `consume_batches(session, *, nomenklatura_id, sklad_id, quantity, method, allow_negative=False, source_document_id=None) -> (list[ConsumedLine], Decimal)`
**Назначение:** списание партий по методу себестоимости; возвращает строки списания
и общую себестоимость. **Технически:** FIFO — `id ASC`, LIFO — `id DESC`, средняя —
средневзвешенная цена; строки партий блокируются `SELECT … FOR UPDATE`. При нехватке —
`InsufficientStockError`, кроме `allow_negative=True` (фиксируется отрицательная партия).

### `register_outgoing(session, *, document_id, date, nomenklatura_id, sklad_id, quantity, amount, consumed=None)`
**Назначение:** движение расхода (без изменения партий); при `consumed` создаётся
движение на каждую списанную партию с `batch_id` (для точной отмены проведения).

### `class InsufficientStockError`
**Назначение:** исключение контроля остатков (поля `nomenklatura_id`, `sklad_id`,
`available`, `required`).

## app/services/document_service.py

### `next_document_number(session, doc_type) -> str`
**Назначение:** следующий номер документа (с префиксом ИБ).

### `create_document(session, *, doc_type, doc_date, ...) -> Document`
**Назначение:** создание документа со строками, пересчёт сумм и НДС.
**Технически:** избегает lazy-load (ставки НДС загружаются явно, итоги считаются
по локальному списку строк).

### `get_document(session, document_id) -> Document | None`
**Назначение:** получение документа.

### `post_document(session, document, user_id=None) -> Document`
**Назначение:** проведение документа (контроль остатков + движения + проводки).
**Технически:** сериализуется advisory-lock'ом (защита от двойного проведения),
для складских документов загружает строки явным запросом (`_load_items`), для
расхода — `_check_stock`, затем `_apply_stock_movement`,
`_apply_money_and_settlement` и `_apply_accounting`; переоценка — `_apply_revaluation`;
статус → «Проведён».

### `unpost_document(session, document, user_id=None) -> Document`
**Назначение:** отмена проведения (обратные движения, восстановление партий).

### `mark_for_deletion(session, document, user_id=None) -> Document`
**Назначение:** пометка на удаление (после отмены проведения).

### Внутренние: `_compute_item_amounts`, `_load_nds_rates`, `_load_items`,
`_check_stock`, `_apply_stock_movement`, `_apply_inventory`, `_apply_revaluation`,
`_rollback_revaluation`, `_apply_money_and_settlement`, `_apply_accounting`,
`_outgoing_stock_cost`, `_incoming_stock_cost`, `_rollback_stock`,
`_delete_movements`

## app/services/report_service.py

### `stock_balances(session) -> list[dict]`
**Назначение:** отчёт «Остатки товаров» по складам.

### `stock_movements(session, start, end, nomenklatura_id=None) -> list[dict]`
**Назначение:** отчёт «Движения товаров» за период.

### `sales_report(session, start, end) -> list[dict]`
**Назначение:** отчёт «Продажи» (проведённые расходные накладные).

### `settlement_balances(session, firma_id=None) -> list[dict]`
**Назначение:** отчёт «Взаиморасчёты» (задолженность контрагентов); опциональный
фильтр по фирме.

### `money_balance(session, firma_id=None) -> Decimal`,
`money_movements(session, start, end, firma_id=None)`
**Назначение:** отчёты по денежным средствам; опциональный фильтр по фирме.

### Сводные показатели дашборда

- `sales_summary(session, start, end) -> dict` — выручка, прибыль, себестоимость,
  количество продаж, средний чек, закупки за период.
- `daily_sales(session, start, end) -> list[dict]` — выручка/прибыль по дням
  (нули в дни без продаж).
- `top_items(session, start, end, limit=10)` — топ товаров по выручке.
- `top_counterparties(session, start, end, limit=10)` — топ клиентов.
- `low_stock(session, threshold=5, limit=10)` — товары с низким/нулевым остатком.
- `recent_sales(session, limit=10)` — последние проведённые продажи.

См. [dashboard](dashboard.md).

## app/core/logging.py

### `setup_logging(level=logging.INFO)`
**Назначение:** единая идемпотентная настройка корневого логгера (stdout).
**Технически:** уровень из настройки `LOG_LEVEL`, замена обработчиков без дублей.

### `get_logger(name) -> Logger`
**Назначение:** логгер модуля с гарантией инициализации логирования.

В `app/main.py` зарегистрированы middleware логирования запросов и единый
обработчик необработанных исключений (логирует traceback, отдаёт 500 без утечки).

## app/bots/* — интеграция ботов

| Модуль | Назначение |
| --- | --- |
| `bots/base.py` | `BotAdapter` (интерфейс), `IncomingMessage` |
| `bots/telegram.py` | `TelegramAdapter` (aiogram 3.x, long polling) |
| `bots/max.py` | `MaxAdapter` (maxapi, long polling) |
| `bots/service.py` | `BotManager`, `store_incoming`, `deliver_outgoing`, `upsert_config` |

**Назначение:** приём сообщений из мессенджеров в чат оператора и отправка
ответов обратно. Настройки (токен, включение) — в админке `/admin/bots`.

См. [bots](bots.md).

## app/models/bot.py

### `class BotConfig`
**Назначение:** конфигурация бота (одна запись на канал: `channel`, `enabled`,
`token`, `name`). Токен — секрет, маскируется в UI.

## app/services/seed_service.py

### `seed_all(session)`
**Назначение:** идемпотентная инициализация начальных данных (роли, валюты,
ставки НДС, единицы, администратор). Вызывается в lifespan приложения.

## app/api/* — REST-маршруты

| Модуль | Эндпоинты |
| --- | --- |
| `api/auth.py` | `POST /api/auth/login` |
| `api/users.py` | CRUD `/api/users`, `/api/users/roles`, `/api/users/permissions` |
| `api/catalog.py` | CRUD справочников `/api/catalog/*`, константы `/api/catalog/constants` |
| `api/documents.py` | `/api/documents` (создание/проведение/отмена/журнал) |
| `api/reports.py` | `/api/reports/*` |

## app/web/* — веб-интерфейс

| Модуль | Страницы |
| --- | --- |
| `web/auth.py` | `/login`, `/logout` |
| `web/admin.py` | `/admin`, `/admin/users`, `/admin/roles`, `/admin/settings`, `/admin/audit`, `/admin/bots`, `/admin/customers` |
| `web/trade.py` | `/`, справочники `/catalog/*` (в т.ч. `/catalog/categories`), документы `/documents`, отчёты `/reports/*` |
| `web/docs.py` | `/admin/docs` (встроенная Markdown-документация) |

## app/web/icons.py — иконки интерфейса

### `ICONS: dict[str, str]`
**Назначение:** декларативный словарь внутренней SVG-разметки иконок (стиль
SF Symbols / Lucide, `viewBox="0 0 24 24"`). Имя → paths.

### `icon(name, size=18, cls="") -> Markup`
**Назначение:** рендерит inline-SVG иконку по имени. **Технически:** возвращает
`markupsafe.Markup` (безопасно вставлять в шаблон без `| safe`); неизвестное имя —
пустая строка (мягкая деградация). Регистрируется как Jinja-глобал `icon` в
[`app/templates.py`](../app/templates.py).

## app/templates/_components.html — переиспользуемые макросы

Библиотека UI-компонентов (Jinja-макросы), импортируемых в шаблоны как
`{% from "_components.html" import ... with context %}`:

| Макрос | Назначение |
| --- | --- |
| `search_input(target, placeholder)` | поле живого поиска по таблице |
| `badge(kind, text)` | статусный бейдж |
| `empty_row(colspan, message)` | строка «пусто» в таблице |
| `empty_state(icon_name, title, hint)` | пустое состояние вне таблицы |
| `modal(id, title)` / `modal_footer(...)` / `modal_end()` | каркас модального окна |
| `field(label, hint)` | поле формы (label + контрол через `caller()`) |

Подробности и правила использования — в [design-system](design-system.md).

## app/services/customer_service.py — клиентский сайт

| Функция | Назначение |
| --- | --- |
| `register(session, phone, password, name)` | регистрация покупателя (телефон — логин) |
| `authenticate(session, phone, password)` | вход покупателя |
| `list_customers`, `get_customer`, `delete_customer` | управление покупателями (админка) |
| `available_products(session, category_id, search)` | товары в наличии (с остатком) |
| `get_cart`, `get_cart_items`, `cart_total`, `add_to_cart`, `set_cart_quantity`, `clear_cart` | корзина |
| `checkout(session, customer)` | подтверждение → создание `ZAKAZ` + очистка корзины |
| `match_kontragent_by_phone(session, phone)` | привязка к контрагенту по телефону |
| `order_context(session, doc)` | контекст заказа для отображения/PDF |

## app/services/pdf_service.py

### `render_order_pdf(order) -> bytes`
**Назначение:** PDF заказа покупателя (WeasyPrint, HTML → PDF).
**Технически:** рендерит шаблон `customer/order_pdf.html` и конвертирует
`HTML(string=...).write_pdf()`. WeasyPrint импортируется лениво.

## app/customer/* — клиентское приложение

| Модуль | Назначение |
| --- | --- |
| `customer/api.py` | REST API `/shop/api/*` (auth, каталог, корзина, заказ, PDF) |
| `customer/web.py` | серверные страницы `/shop/*` |
| `customer/miniapp.py` | вход MiniApp `GET /shop/mini` (initData → cookie покупателя) |
| `customer/deps.py` | `get_current_customer` (JWT покупателя из cookie/Bearer) |
| `customer/app.py` | `create_customer_app()` (монтируется в main по `/shop`) |

См. также [customer](customer.md).

## app/services/miniapp_service.py — MiniApp

### `validate_init_data(channel, init_data, secret) -> dict | None`
**Назначение:** проверяет подпись initData мессенджера (Telegram `hash` —
HMAC_SHA256(bot_token, "WebAppData"); MAX `sign` — HMAC_SHA256 со секретом).
Возвращает `{channel, external_id, name}` или `None`.

### `make_test_init_data(channel, secret, user_id, name)` — собирает валидный
initData (для тестов и локальной проверки).

### `find_or_create_customer(session, channel, external_id, name) -> Customer`
**Назначение:** находит покупателя по привязке или создаёт нового (синтетический
логин) и создаёт `CustomerBinding`.

## app/models/customer.py

### `class Customer`, `class Cart`, `class CartItem`
**Назначение:** учётные записи покупателей и корзина (отдельные от сотрудников).

### `class CustomerBinding`
**Назначение:** привязка аккаунта мессенджера (`channel + external_id`) к
покупателю — для MiniApp.

## app/models/catalog/category.py

### `class Category`
**Назначение:** иерархический справочник категорий товаров (привязка
`Nomenklatura.category_id`).

## app/models/agent.py — управление AI-агентом

Плоскость управления агентом (сам агент — отдельный контейнер).

| Модель | Таблица | Назначение |
| --- | --- | --- |
| `AgentConfig` | `agent_configs` | глобальные настройки (модель, temperature, пороги) |
| `AgentPrompt` / `AgentPromptVersion` | `agent_prompts` / `agent_prompt_versions` | версионируемые промпты |
| `AgentTool` | `agent_tools` | реестр инструментов (эндпоинт, права, политика одобрения) |
| `AgentApiKey` | `agent_api_keys` | API-ключи (хранится только SHA-256 хеш) |
| `AgentRun` | `agent_runs` | журнал запусков (аудит/трассировка) |
| `AgentApproval` | `agent_approvals` | очередь одобрений (human-in-the-loop) |

Константы: `DEFAULT_AGENT_CONFIG`, `DEFAULT_PROMPTS`, `DEFAULT_TOOLS`,
`APPROVAL_POLICIES` (`auto`/`threshold`/`always`).

## app/services/agent_service.py

| Функция | Назначение |
| --- | --- |
| `get_configs` / `set_config` / `set_configs` | настройки агента |
| `list_prompts` / `get_prompt` / `create_prompt` | промпты (с eager-load версий) |
| `add_prompt_version` / `activate_prompt_version` | версионирование + откат |
| `list_tools` / `get_tool` / `update_tool` | инструменты |
| `list_keys` / `create_key` / `set_key_enabled` / `delete_key` / `verify_key` | API-ключи (SHA-256) |
| `list_runs` / `list_approvals` / `get_approval` / `decide_approval` | журнал и одобрения |
| `seed_agent` | идемпотентный сид дефолтных промптов/инструментов |

## app/web/agent_admin.py — админка AI-агента

Маршруты (доступны только администратору):

| Маршрут | Назначение |
| --- | --- |
| `GET/POST /admin/agent` | обзор + конфигурация |
| `/admin/agent/prompts` (+ `/{id}/version`, `/{id}/activate`) | промпты и версии |
| `/admin/agent/tools` (+ `/{id}`) | инструменты |
| `/admin/agent/keys` (+ `/{id}/toggle`, `/{id}/delete`) | API-ключи |
| `/admin/agent/runs` | журнал запусков |
| `/admin/agent/approvals` (+ `/{id}/decide`) | одобрения |

См. [ai-agent](ai-agent.md).

## app/models/site.py — управление сайтом/MiniApp

| Модель | Таблица | Назначение |
| --- | --- | --- |
| `SiteSetting` | `site_settings` | настройки видимости (логотип, баннер, оформление карточек) |
| `Promotion` | `promotions` | акция: скидка (`percent`/`fixed`) на товар/категорию/всё |

Константы: `DEFAULT_SITE_SETTINGS`, `DISCOUNT_TYPES`. Также добавлено поле
`Nomenklatura.is_published` (публикация товара на сайте) и `Message.is_read`
(непрочитанные сообщения чата).

## app/services/site_service.py

| Функция | Назначение |
| --- | --- |
| `get_settings` / `set_settings` | настройки сайта (с дефолтами) |
| `list_promotions` / `get_promotion` / `create_promotion` / `update_promotion` / `delete_promotion` | CRUD акций |
| `find_promotion(promos, nomenklatura_id, category_id, on)` | чистая функция выбора активной акции (товар → категория → глобальная) |
| `promotion_for(...)` | обёртка `find_promotion` с загрузкой из БД |
| `apply_discount(base_price, promo)` | цена после скидки (не ниже нуля) |

## app/web/site_admin.py — админка сайта/MiniApp

Маршруты (только администратор): `/admin/site` (обзор), `/admin/site/settings`,
`/admin/site/logo`, `/admin/site/banner` (загрузка изображений),
`/admin/site/promotions` (+ `/{id}/toggle`, `/{id}/delete`),
`/admin/site/products/{id}/toggle` (публикация товара).

## app/services/image_service.py — загрузка изображений

### `detect_ext(data) -> str | None`
**Назначение:** определение формата по сигнатуре (PNG/JPEG/GIF/WebP). WebP
определяется по `RIFF` + `WEBP` (отличается от WAV). **Технически:** сравнение
магических байтов.

### `save_image(file, prefix) -> str | None`
**Назначение:** валидация и сохранение изображения (ограничение размера,
проверка сигнатуры, без перекодирования — прозрачность/альфа-канал WebP-стикеров
сохраняется). Используется загрузкой фото товара, логотипа и баннера.

## app/static/js/app.js — фронтенд-диалоги

### `confirmDialog(message, opts) -> Promise<boolean>`
### `notify(message, opts)`
### `confirmSubmit(form, message, opts)`
**Назначение:** стилизованные модальные окна (с размытием фона) для
уведомлений и подтверждений — вместо системных `alert()`/`confirm()`.

### `animateCounters(root?)`
**Назначение:** плавная анимация чисел у элементов с атрибутом `data-counter`
(с учётом `prefers-reduced-motion`). Атрибуты: `data-counter` (число),
`data-counter-decimals`, `data-counter-prefix`.

### Переключатель темы (`#theme-toggle`)
**Назначение:** переключение светлой/тёмной темы. Значение хранится в
`localStorage` (`uwu-theme`), ранняя установка `data-theme` — в `<head>` шаблонов,
чтобы исключить «мигание» при загрузке. См. [design-system](design-system.md).

См. также [api](api.md) и [security](security.md).
