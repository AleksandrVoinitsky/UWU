# Тестирование

## Подход

TDD: тесты пишутся как часть системы и используются как проверка готовности
перед деплоем. Интеграционные тесты выполняются против реального PostgreSQL
(тестовая БД `uwu_test`), что проверяет SQL, транзакции и партионный учёт
целиком.

## Запуск

```bash
# Тестовая БД (Docker)
docker run -d --name uwu-test-pg -e POSTGRES_USER=uwu -e POSTGRES_PASSWORD=uwu \
  -e POSTGRES_DB=uwu_test -p 5433:5432 postgres:16-alpine

# Создать схему и прогнать тесты
export DATABASE_URL=postgresql+asyncpg://uwu:uwu@localhost:5433/uwu_test
pytest tests/ -v
```

Подключение к тестовой БД задаётся переменной `DATABASE_URL` (см.
`tests/conftest.py`). Тестовый движок пересоздаётся с `NullPool` — это решает
проблему привязки соединений asyncpg к event loop на Windows.

## Структура

| Файл | Покрытие |
| --- | --- |
| `tests/test_auth.py` | Вход, неверный пароль, неизвестный пользователь |
| `tests/test_api_auth.py` | Аутентификация REST API (401/200) |
| `tests/test_catalog.py` | Автокоды, создание справочников через API |
| `tests/test_documents.py` | Приход, расход (FIFO), контроль остатков, перемещение, отмена проведения, взаиморасчёты, печатные формы |
| `tests/test_reports.py` | Остатки, взаиморасчёты, деньги |
| `tests/test_users.py` | Сид админа/ролей, CRUD пользователей, защита от удаления админа |
| `tests/test_security.py` | Настройки безопасности (секреты, токены) |
| `tests/test_numbering.py` | Нумерация документов (advisory-lock) |
| `tests/test_prices.py` | Ценообразование (автонаценка, явные цены) |
| `tests/test_dashboard.py` | Дашборд, KPI, графики |
| `tests/test_customer.py` | Покупатель: регистрация, вход, корзина, заказ |
| `tests/test_miniapp.py` | MiniApp (Telegram/MAX) initData, привязка |
| `tests/test_bots.py` | Боты: фабрика, чаты, доставка сообщений |
| `tests/test_chat.py` | Мессенджер (чаты, сообщения) |
| `tests/test_bugfix.py` | Регрессионные тесты багфиксов |
| `tests/test_encoding.py` | Кодировки (mojibake) |
| `tests/test_logging.py` | Логирование |
| `tests/test_csv.py` | CSV-экспорт, защита от формульной инъекции |
| `tests/test_audit_fixes.py` | Регрессионные тесты на находки аудита (XSS, себестоимость, права, rate limiting, CSRF, отмена проведения FIFO и др.) |

## Ключевые проверяемые сценарии

- **Проведение прихода** обновляет остатки.
- **FIFO** — при двух партиях с разной ценой расход списывает партию по
  меньшей/старейшей цене.
- **Контроль остатков** — расход сверх остатка даёт `InsufficientStockError`.
- **Перемещение** — переносит остаток между складами.
- **Отмена проведения** — восстанавливает остатки.
- **Взаиморасчёты** — продажа в кредит формирует задолженность контрагента.

## Фикстуры (`tests/conftest.py`)

- `_setup_db` — создаёт схему БД (session-scoped).
- `_clean_db` — очищает таблицы перед каждым тестом.
- `session` / `seeded_session` — сессия, опционально с начальными данными.
- `client` — ASGI-клиент (httpx) для тестов API.
- `admin_token` / `admin_headers` — аутентификация администратора.
