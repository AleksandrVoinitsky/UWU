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

### `consume_batches(session, *, nomenklatura_id, sklad_id, quantity, method) -> (list[ConsumedLine], Decimal)`
**Назначение:** списание партий по методу себестоимости; возвращает строки списания
и общую себестоимость. **Технически:** FIFO — `id ASC`, LIFO — `id DESC`, средняя —
средневзвешенная цена. При нехватке — `InsufficientStockError`.

### `register_outgoing(session, *, document_id, date, nomenklatura_id, sklad_id, quantity, amount)`
**Назначение:** движение расхода (без изменения партий).

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

### `post_document(session, document) -> Document`
**Назначение:** проведение документа (контроль остатков + движения).
**Технически:** для складских документов загружает строки явным запросом
(`_load_items`), для расхода — `_check_stock`, затем `_apply_stock_movement` и
`_apply_money_and_settlement`; статус → «Проведён».

### `unpost_document(session, document) -> Document`
**Назначение:** отмена проведения (обратные движения, восстановление партий).

### `mark_for_deletion(session, document) -> Document`
**Назначение:** пометка на удаление (после отмены проведения).

### Внутренние: `_compute_item_amounts`, `_load_nds_rates`, `_load_items`,
`_check_stock`, `_apply_stock_movement`, `_apply_money_and_settlement`,
`_rollback_stock`, `_delete_movements`

## app/services/report_service.py

### `stock_balances(session) -> list[dict]`
**Назначение:** отчёт «Остатки товаров» по складам.

### `stock_movements(session, start, end, nomenklatura_id=None) -> list[dict]`
**Назначение:** отчёт «Движения товаров» за период.

### `sales_report(session, start, end) -> list[dict]`
**Назначение:** отчёт «Продажи» (проведённые расходные накладные).

### `settlement_balances(session) -> list[dict]`
**Назначение:** отчёт «Взаиморасчёты» (задолженность контрагентов).

### `money_balance(session) -> Decimal`, `money_movements(session, start, end)`
**Назначение:** отчёты по денежным средствам.

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
| `customer/deps.py` | `get_current_customer` (JWT покупателя из cookie/Bearer) |
| `customer/app.py` | `create_customer_app()` (монтируется в main по `/shop`) |

См. также [customer](customer.md).

## app/models/customer.py

### `class Customer`, `class Cart`, `class CartItem`
**Назначение:** учётные записи покупателей и корзина (отдельные от сотрудников).

## app/models/catalog/category.py

### `class Category`
**Назначение:** иерархический справочник категорий товаров (привязка
`Nomenklatura.category_id`).

См. также [api](api.md) и [security](security.md).
